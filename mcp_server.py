import os
from typing import Optional
import uvicorn
from fastmcp import FastMCP
from optimizer.ast_engine import ASTSymbolEngine
from optimizer.dead_code import DeadCodeAuditor
from optimizer.dependency_auditor import DependencyAuditor

mcp = FastMCP("Codebase Optimizer")

AUTO_RUN = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}

@mcp.tool(annotations=AUTO_RUN)
def get_file_outline(file_path: str) -> str:
    """Returns compact signatures and docstrings of a Python file, cutting tokens by up to 85%."""
    if not os.path.exists(file_path):
        return f"Error: File '{file_path}' does not exist."
    with open(file_path, "r", encoding="utf-8") as f:
        code = f.read()
    return ASTSymbolEngine.get_outline(code)

@mcp.tool(annotations=AUTO_RUN)
def get_symbol_slice(file_path: str, symbol_name: str) -> str:
    """Extracts a targeted function or class with its required top-level imports."""
    if not os.path.exists(file_path):
        return f"Error: File '{file_path}' does not exist."
    with open(file_path, "r", encoding="utf-8") as f:
        code = f.read()
    return ASTSymbolEngine.get_symbol_slice(code, symbol_name)

@mcp.tool(annotations=AUTO_RUN)
def find_dead_exports(directory_path: str = ".") -> str:
    """Scans a directory for functions/classes exported in a file but never referenced in other files."""
    results = DeadCodeAuditor.scan_directory(directory_path)
    if not results:
        return "Clean codebase: No unreferenced dead exports detected."

    lines = ["Detected Dead Exports:"]
    for file, symbols in results.items():
        lines.append(f"- {file}: {', '.join(symbols)}")
    return "\n".join(lines)

@mcp.tool(annotations=AUTO_RUN)
def audit_dependencies(directory_path: str = ".", req_file: str = "requirements.txt") -> str:
    """Checks requirements.txt against actual imports across all files to find ghost dependencies."""
    report = DependencyAuditor.audit_requirements(directory_path, req_file)
    if "error" in report:
        return report["error"][0]

    ghosts = report.get("potential_ghost_dependencies", [])
    if not ghosts:
        return "All declared dependencies appear to be imported."

    return f"Detected Ghost Dependencies ({len(ghosts)}):\n" + "\n".join([f"  - {g}" for g in ghosts])

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    mcp.run()
