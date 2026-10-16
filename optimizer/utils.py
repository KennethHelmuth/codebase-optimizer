import ast
import os
from typing import List, Tuple

IGNORE_DIRS = {
    ".git", "__pycache__", "venv", ".venv", "env",
    "node_modules", "build", "dist", ".pytest_cache", ".mypy_cache"
}


def iter_python_files(root_dir: str) -> List[Tuple[str, str, ast.Module, str]]:
    """
    Walks root_dir (ignoring IGNORE_DIRS) and returns a list of
    (full_path, rel_path, parsed_ast, raw_code) for all valid Python files.
    """
    parsed_files: List[Tuple[str, str, ast.Module, str]] = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in sorted(dirnames) if d not in IGNORE_DIRS]
        for fname in sorted(filenames):
            if not fname.endswith(".py"):
                continue
            full_path = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(full_path, root_dir)
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    code = f.read()
                tree = ast.parse(code, filename=rel_path)
                parsed_files.append((full_path, rel_path, tree, code))
            except Exception:
                continue
    return parsed_files
