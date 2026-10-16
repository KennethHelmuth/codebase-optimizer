import argparse
import hmac
import ipaddress
import os
import sys
from typing import Optional, Tuple
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


def _resolve_safe_path(user_path: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Resolves `user_path` using os.path.realpath and verifies it resides inside
    the configured `MCP_ALLOWED_ROOT` (defaults to current working directory).
    Rejects path traversal (`..`) and symlink escapes outside the allowed root.
    """
    allowed_root_raw = os.environ.get("MCP_ALLOWED_ROOT") or os.getcwd()
    allowed_root = os.path.realpath(allowed_root_raw)

    if os.path.isabs(user_path):
        candidate = os.path.realpath(user_path)
    else:
        candidate = os.path.realpath(os.path.join(allowed_root, user_path))

    try:
        common = os.path.commonpath([allowed_root, candidate])
    except ValueError:
        return None, f"Error: Access denied. Path '{user_path}' is outside MCP_ALLOWED_ROOT ('{allowed_root}')."

    if common != allowed_root:
        return None, f"Error: Access denied. Path '{user_path}' resolves outside MCP_ALLOWED_ROOT ('{allowed_root}')."

    return candidate, None


@mcp.tool(annotations=AUTO_RUN)
def get_repo_map(directory_path: str = ".", max_files: int = 100) -> str:
    """Generates a hierarchical AST symbol map of the repository with token compression telemetry."""
    safe_dir, err = _resolve_safe_path(directory_path)
    if err:
        return err
    return ASTSymbolEngine.get_repo_map(safe_dir, max_files=max_files)


@mcp.tool(annotations=AUTO_RUN)
def get_file_outline(file_path: str) -> str:
    """Extracts compact signatures, type hints, line ranges, and docstrings of a Python file."""
    safe_file, err = _resolve_safe_path(file_path)
    if err:
        return err
    if not os.path.exists(safe_file):
        return f"Error: File '{file_path}' does not exist."
    if not os.path.isfile(safe_file):
        return f"Error: Path '{file_path}' is not a regular file."
    with open(safe_file, "r", encoding="utf-8") as f:
        code = f.read()
    return ASTSymbolEngine.get_outline(code)


@mcp.tool(annotations=AUTO_RUN)
def get_symbol_slice(file_path: str, symbol_name: str) -> str:
    """Extracts a target function/class plus its transitive local helper dependencies and filtered imports."""
    safe_file, err = _resolve_safe_path(file_path)
    if err:
        return err
    if not os.path.exists(safe_file):
        return f"Error: File '{file_path}' does not exist."
    if not os.path.isfile(safe_file):
        return f"Error: Path '{file_path}' is not a regular file."
    with open(safe_file, "r", encoding="utf-8") as f:
        code = f.read()
    return ASTSymbolEngine.get_symbol_slice(code, symbol_name)


@mcp.tool(annotations=AUTO_RUN)
def compress_git_diff(raw_diff: str) -> str:
    """Strips lockfiles, minified bundles, and boilerplate noise from unified git diffs."""
    return ContextPruner.compress_git_diff(raw_diff)


@mcp.tool(annotations=AUTO_RUN)
def audit_ai_slop(directory_path: str = ".") -> str:
    """Runs AST clone detection across files, unreferenced dead export analysis, and pass-through wrapper checks."""
    safe_dir, err = _resolve_safe_path(directory_path)
    if err:
        return err
    return SlopAuditor.format_slop_report(safe_dir)


@mcp.tool(annotations=AUTO_RUN)
def scan_runtime_hotspots(directory_path: str = ".") -> str:
    """Scans for loop I/O bottlenecks, sequential awaits, high cognitive complexity, and heavy top-level imports."""
    safe_dir, err = _resolve_safe_path(directory_path)
    if err:
        return err
    return HotspotScanner.format_hotspot_report(safe_dir)


@mcp.tool(annotations=AUTO_RUN)
def audit_dependencies(directory_path: str = ".") -> str:
    """Reconciles requirements.txt and pyproject.toml against actual AST imports and detects orphaned modules."""
    safe_dir, err = _resolve_safe_path(directory_path)
    if err:
        return err
    dep_report = DependencyAuditor.audit_requirements(safe_dir)
    orphans = DependencyAuditor.find_orphan_files(safe_dir)

    lines = [
        f"Declared Packages: {dep_report.get('declared_packages', [])}",
        f"Ghost Dependencies: {dep_report.get('potential_ghost_dependencies', [])}",
        f"Undeclared Imports: {dep_report.get('undeclared_third_party_imports', [])}",
        f"Orphan Files: {orphans}",
    ]
    if dep_report.get("warnings"):
        lines.append(f"Warnings: {dep_report['warnings']}")
    return "\n".join(lines)


@mcp.tool(annotations=AUTO_RUN)
def get_health_scorecard(directory_path: str = ".") -> str:
    """Computes a deterministic 0-100 Codebase Health Scorecard (Grade A+ to F) with a prioritized remediation checklist."""
    safe_dir, err = _resolve_safe_path(directory_path)
    if err:
        return err
    return HealthScorer.format_health_report(safe_dir)


class TokenAuthMiddleware(BaseHTTPMiddleware):
    """
    Constant-time Bearer token authentication middleware.
    Rejects query-string tokens (`?token=...`) to prevent token leakage in logs.
    """

    def __init__(self, app, token: str):
        super().__init__(app)
        self.expected_token = token.encode("utf-8")

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/health":
            return JSONResponse({"status": "ok"})

        if not self.expected_token:
            return await call_next(request)

        # Reject if token is passed via query string
        if "token" in request.query_params:
            return JSONResponse(
                {"error": "Query-string tokens are forbidden. Use 'Authorization: Bearer <token>'."},
                status_code=401,
            )

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse({"error": "Missing or invalid Authorization Bearer header."}, status_code=401)

        provided_token = auth_header[len("Bearer ") :].strip().encode("utf-8")
        if not hmac.compare_digest(provided_token, self.expected_token):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        return await call_next(request)


def _is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_http_bind(host: str, token: str) -> None:
    """Refuses to bind HTTP to a non-loopback address unless MCP_TOKEN is configured."""
    if not _is_loopback_host(host) and not token.strip():
        raise RuntimeError(
            f"Refusing to start HTTP server on non-loopback host '{host}' without MCP_TOKEN set. "
            "Set MCP_TOKEN in the environment or bind to 127.0.0.1."
        )


def create_http_app(token: Optional[str] = None) -> Starlette:
    mcp_app = mcp.http_app(path="/mcp")
    resolved_token = token if token is not None else os.environ.get("MCP_TOKEN", "")
    app = Starlette(routes=[Mount("/", app=mcp_app)], lifespan=mcp_app.lifespan)
    if resolved_token:
        app.add_middleware(TokenAuthMiddleware, token=resolved_token)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Codebase Optimizer MCP Server")
    parser.add_argument(
        "--http",
        action="store_true",
        help="Run over Streamable HTTP instead of default stdio transport.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="HTTP bind host when --http is enabled (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "8000")),
        help="HTTP port when --http is enabled (default: 8000).",
    )
    args = parser.parse_args()

    if args.http:
        token = os.environ.get("MCP_TOKEN", "")
        validate_http_bind(args.host, token)
        http_app = create_http_app(token=token)
        uvicorn.run(http_app, host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
