import ast
import os
from typing import Dict, List, Optional, Set, Tuple


class ASTSymbolEngine:
    """Extracts outlines, signatures, and symbol slices from Python source files."""

    @staticmethod
    def get_outline(code: str) -> str:
        """Extracts top-level and class-level signatures, docstrings, and fields, discarding implementation bodies."""
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return f"# SyntaxError parsing file: {e}"

        lines = []
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
                args = ast.unparse(node.args)
                returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
                doc = ast.get_docstring(node)
                doc_str = f'    """{doc}"""\n' if doc else ""
                lines.append(f"{prefix} {node.name}({args}){returns}:\n{doc_str}    ...")

            elif isinstance(node, ast.ClassDef):
                bases = f"({', '.join(ast.unparse(b) for b in node.bases)})" if node.bases else ""
                lines.append(f"class {node.name}{bases}:")
                doc = ast.get_docstring(node)
                if doc:
                    lines.append(f'    """{doc}"""')

                class_members = 0
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        pfx = "async def" if isinstance(item, ast.AsyncFunctionDef) else "def"
                        args = ast.unparse(item.args)
                        ret = f" -> {ast.unparse(item.returns)}" if item.returns else ""
                        lines.append(f"    {pfx} {item.name}({args}){ret}: ...")
                        class_members += 1
                    elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        lines.append(f"    {item.target.id}: {ast.unparse(item.annotation)}")
                        class_members += 1

                if class_members == 0 and not doc:
                    lines.append("    ...")

            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        lines.append(f"{target.id} = ...")

        return "\n\n".join(lines) if lines else "# No top-level classes or functions found."

    @staticmethod
    def get_symbol_slice(code: str, symbol_name: str) -> str:
        """Extracts the exact code block for a given symbol name and its immediately required imports."""
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return f"# SyntaxError: {e}"

        # Collect top-level imports
        imports = []
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.append(ast.unparse(node))

        target_node = None
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name == symbol_name:
                    target_node = node
                    break
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == symbol_name:
                        target_node = node
                        break

        if not target_node:
            return f"# Error: Symbol '{symbol_name}' not found."

        import_header = "\n".join(imports)
        symbol_code = ast.unparse(target_node)
        return f"{import_header}\n\n# --- Sliced Symbol: {symbol_name} ---\n{symbol_code}"
