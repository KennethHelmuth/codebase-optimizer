import os
from typing import Optional
import uvicorn
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount
from fastmcp import FastMCP

from optimizer.ast_engine import ASTSymbolEngine
from optimizer.context_pruner import ContextPruner
from optimizer.slop_auditor import SlopAuditor
from optimizer.hotspot_scanner import HotspotScanner
from optimizer.dependency_auditor import DependencyAuditor
from optimizer.health_scorer import HealthScorer

# Initialize FastMCP Server
mcp = FastMCP("Codebase Optimizer")

# Zero-prompt execution annotations for Gemini and MCP clients
AUTO_RUN = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}

@mcp.tool(annotations=AUTO_RUN)
def get_repo_map(directory_path: str = ".") -> str:
    """Generates a hierarchical AST symbol map of the repository in under 500 tokens with token compression telemetry."""
    return ASTSymbolEngine.get_repo_map(directory_path)

@mcp.tool(annotations=AUTO_RUN)
def get_file_outline(file_path: str) -> str:
    """Extracts compact signatures, type hints, line ranges, and docstrings of a Python file, cutting tokens by up to 85%."""
    if not os.path.exists(file_path):
        return f"Error: File '{file_path}' does not exist."
    with open(file_path, "r", encoding="utf-8") as f:
        code = f.read()
    return ASTSymbolEngine.get_outline(code)

@mcp.tool(annotations=AUTO_RUN)
def get_symbol_slice(file_path: str, symbol_name: str) -> str:
    """Extracts a target function/class plus its transitive local helper dependencies and filtered imports."""
    if not os.path.exists(file_path):
        return f"Error: File '{file_path}' does not exist."
    with open(file_path, "r", encoding="utf-8") as f:
        code = f.read()
    return ASTSymbolEngine.get_symbol_slice(code, symbol_name)

@mcp.tool(annotations=AUTO_RUN)
def compress_git_diff(raw_diff: str) -> str:
    """Strips lockfiles, minified bundles, and boilerplate noise from unified git diffs."""
    return ContextPruner.compress_git_diff(raw_diff)

@mcp.tool(annotations=AUTO_RUN)
def audit_ai_slop(directory_path: str = ".") -> str:
    """Runs AST clone detection across files, unreferenced dead export analysis, and pass-through wrapper checks."""
    return SlopAuditor.format_slop_report(directory_path)

@mcp.tool(annotations=AUTO_RUN)
def scan_runtime_hotspots(directory_path: str = ".") -> str:
    """Scans for loop I/O bottlenecks, sequential awaits, high cognitive complexity, and heavy top-level imports."""
    return HotspotScanner.format_hotspot_report(directory_path)

@mcp.tool(annotations=AUTO_RUN)
def audit_dependencies(directory_path: str = ".") -> str:
    """Reconciles requirements.txt and pyproject.toml against actual AST imports and detects orphaned modules."""
    dep_report = DependencyAuditor.audit_requirements(directory_path)
    orphans = DependencyAuditor.find_orphan_files(directory_path)
    
    lines = [
        f"Declared Packages: {dep_report.get('declared_packages', [])}",
        f"Ghost Dependencies: {dep_report.get('potential_ghost_dependencies', [])}",
        f"Undeclared Imports: {dep_report.get('undeclared_third_party_imports', [])}",
        f"Orphan Files: {orphans}"
    ]
    return "\n".join(lines)

@mcp.tool(annotations=AUTO_RUN)
def get_health_scorecard(directory_path: str = ".") -> str:
    """Computes a deterministic 0-100 Codebase Health Scorecard (Grade A+ to F) with a prioritized remediation checklist."""
    return HealthScorer.format_health_report(directory_path)


# Optional token authentication middleware for secure remote hosting (Render / Fly.io)
MCP_SECRET_TOKEN = os.environ.get("MCP_TOKEN", "")

class TokenAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not MCP_SECRET_TOKEN or request.url.path == "/health":
            return JSONResponse({"status": "ok"})
            
        query_token = request.query_params.get("token")
        auth_header = request.headers.get("Authorization", "")
        bearer_token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else None

        if query_token != MCP_SECRET_TOKEN and bearer_token != MCP_SECRET_TOKEN:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        return await call_next(request)


# Expose MCP app at /mcp
mcp_app = mcp.http_app(path="/mcp")
app = Starlette(routes=[Mount("/", app=mcp_app)], lifespan=mcp_app.lifespan)
if MCP_SECRET_TOKEN:
    app.add_middleware(TokenAuthMiddleware)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
