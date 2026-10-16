import ast
import os
from typing import Dict, List, Set, Tuple


class DeadCodeAuditor:
    """Detects symbols defined in Python files that are never imported or referenced elsewhere."""

    @staticmethod
    def scan_directory(root_dir: str) -> Dict[str, List[str]]:
        """Scans all Python files in a directory for unreferenced exports."""
        defined_symbols: Dict[str, Set[str]] = {}  # filepath -> set of symbols
        all_referenced_symbols: Set[str] = set()

        # Step 1: Collect all defined symbols per file
        for dirpath, _, filenames in os.walk(root_dir):
            if any(p in dirpath for p in [".git", "__pycache__", "venv", ".venv", "build", "dist"]):
                continue

            for fname in filenames:
                if not fname.endswith(".py"):
                    continue

                full_path = os.path.join(dirpath, fname)
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        tree = ast.parse(f.read(), filename=full_path)
                except Exception:
                    continue

                symbols = set()
                for node in tree.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        # Skip private symbols starting with underscore unless __all__ or dunder
                        if not node.name.startswith("_"):
                            symbols.add(node.name)

                defined_symbols[full_path] = symbols

        # Step 2: Collect all symbol references across all files
        for dirpath, _, filenames in os.walk(root_dir):
            if any(p in dirpath for p in [".git", "__pycache__", "venv", ".venv"]):
                continue

            for fname in filenames:
                if not fname.endswith(".py"):
                    continue

                full_path = os.path.join(dirpath, fname)
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        tree = ast.parse(f.read(), filename=full_path)
                except Exception:
                    continue

                for node in ast.walk(tree):
                    if isinstance(node, ast.Name):
                        all_referenced_symbols.add(node.id)
                    elif isinstance(node, ast.Attribute):
                        all_referenced_symbols.add(node.attr)
                    elif isinstance(node, ast.alias):
                        all_referenced_symbols.add(node.name)

        # Step 3: Find definitions that have zero references in other files
        # Note: If a symbol is referenced, it appears in all_referenced_symbols (including its own def).
        # We check if it appears in files OTHER than its origin.
        dead_exports: Dict[str, List[str]] = {}
        for file_path, symbols in defined_symbols.items():
            file_dead = []
            for sym in symbols:
                # Count occurrences across files
                references_outside = 0
                for other_file, _ in defined_symbols.items():
                    if other_file == file_path:
                        continue
                    try:
                        with open(other_file, "r", encoding="utf-8") as f:
                            content = f.read()
                            if sym in content:
                                references_outside += 1
                                break
                    except Exception:
                        pass

                if references_outside == 0:
                    file_dead.append(sym)

            if file_dead:
                rel_path = os.path.relpath(file_path, root_dir)
                dead_exports[rel_path] = file_dead

        return dead_exports
