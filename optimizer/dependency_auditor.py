import ast
import os
import re
from typing import Dict, List, Set


class DependencyAuditor:
    """Audits requirements.txt / pyproject.toml against actual codebase imports."""

    STD_LIB = {
        "os", "sys", "re", "math", "time", "datetime", "typing", "collections",
        "itertools", "functools", "json", "ast", "pathlib", "subprocess", "shutil",
        "glob", "logging", "tempfile", "urllib", "http", "socket", "asyncio",
        "hashlib", "base64", "uuid", "io", "copy", "traceback", "inspect", "enum"
    }

    @staticmethod
    def extract_imported_packages(root_dir: str) -> Set[str]:
        """Extracts top-level package names imported anywhere in the project."""
        packages = set()

        for dirpath, _, filenames in os.walk(root_dir):
            if any(p in dirpath for p in [".git", "__pycache__", "venv", ".venv"]):
                continue

            for fname in filenames:
                if not fname.endswith(".py"):
                    continue

                full_path = os.path.join(dirpath, fname)
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        tree = ast.parse(f.read())
                except Exception:
                    continue

                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            pkg = alias.name.split(".")[0]
                            packages.add(pkg)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            pkg = node.module.split(".")[0]
                            packages.add(pkg)

        return packages

    @staticmethod
    def audit_requirements(root_dir: str, req_file_name: str = "requirements.txt") -> Dict[str, List[str]]:
        """Compares packages in requirements.txt with imported packages."""
        req_path = os.path.join(root_dir, req_file_name)
        if not os.path.exists(req_path):
            return {"error": [f"File {req_file_name} not found in {root_dir}."]}

        listed_packages = set()
        with open(req_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Match package name before versions/comparators
                match = re.match(r"^([a-zA-Z0-9_\-]+)", line)
                if match:
                    pkg = match.group(1).lower().replace("-", "_")
                    listed_packages.add(pkg)

        imported = DependencyAuditor.extract_imported_packages(root_dir)
        imported_normalized = {p.lower().replace("-", "_") for p in imported}

        unused = []
        for pkg in listed_packages:
            # Simple heuristic mapping for common variations (e.g. pygithub -> github)
            if pkg == "pygithub" and "github" in imported_normalized:
                continue
            if pkg == "tree_sitter" and "tree_sitter" in imported_normalized:
                continue

            if pkg not in imported_normalized and pkg not in DependencyAuditor.STD_LIB:
                unused.append(pkg)

        return {
            "declared_packages": sorted(list(listed_packages)),
            "actually_imported": sorted(list(imported_normalized)),
            "potential_ghost_dependencies": sorted(unused),
        }
