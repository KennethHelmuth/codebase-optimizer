import ast
import os
from typing import Dict, List, Optional, Set, Tuple


class ASTSymbolEngine:
    """
    Phase 1: Context Diet & AST Slicing Engine.
    Extracts dense repo maps, compact file outlines, and transitive symbol slices
    with token compression telemetry.
    """

    IGNORE_DIRS = {
        ".git", "__pycache__", "venv", ".venv", "env",
        "node_modules", "build", "dist", ".pytest_cache", ".mypy_cache"
    }

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Fast heuristic token estimator (~4 chars per token for code)."""
        if not text:
            return 0
        return max(1, len(text) // 4)

    @classmethod
    def compression_stats(cls, raw_code: str, compressed_code: str) -> str:
        """Returns a single-line telemetry header showing token savings."""
        raw_t = cls.estimate_tokens(raw_code)
        comp_t = cls.estimate_tokens(compressed_code)
        saved_pct = round((1 - (comp_t / max(1, raw_t))) * 100, 1)
        return f"# [Token Diet] Raw: ~{raw_t} tokens -> Compressed: ~{comp_t} tokens ({saved_pct}% saved)"

    @classmethod
    def get_repo_map(cls, root_dir: str, max_files: int = 100) -> str:
        """
        1.1 Compact Repo Skeleton:
        Generates a dense, hierarchical symbol index of the entire repository
        so agents can locate classes and functions in <500 tokens.
        """
        if not os.path.exists(root_dir):
            return f"# Error: Directory '{root_dir}' does not exist."

        lines = [f"# Repository Skeleton Map: {os.path.abspath(root_dir)}"]
        total_raw_chars = 0
        file_count = 0

        for dirpath, dirnames, filenames in os.walk(root_dir):
            dirnames[:] = [d for d in sorted(dirnames) if d not in cls.IGNORE_DIRS]

            for fname in sorted(filenames):
                if not fname.endswith(".py"):
                    continue

                full_path = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(full_path, root_dir)

                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        code = f.read()
                    total_raw_chars += len(code)
                    tree = ast.parse(code)
                except Exception:
                    continue

                file_symbols = []
                for node in tree.body:
                    if isinstance(node, ast.ClassDef):
                        methods = [
                            m.name for m in node.body
                            if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                            and (not m.name.startswith("_") or m.name == "__init__")
                        ]
                        method_str = f" [{', '.join(methods)}]" if methods else ""
                        file_symbols.append(f"  class {node.name}{method_str}")
                    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        pfx = "async fn" if isinstance(node, ast.AsyncFunctionDef) else "fn"
                        file_symbols.append(f"  {pfx} {node.name}()")

                lines.append(f"\n📄 {rel_path}")
                if file_symbols:
                    lines.extend(file_symbols)
                else:
                    lines.append("  (module constants / scripts only)")

                file_count += 1
                if file_count >= max_files:
                    lines.append(f"\n# ... truncated after {max_files} files")
                    break

        map_output = "\n".join(lines)
        raw_tokens = max(1, total_raw_chars // 4)
        map_tokens = cls.estimate_tokens(map_output)
        saved = round((1 - (map_tokens / raw_tokens)) * 100, 1)
        header = (
            f"# [Repo Map Telemetry] Indexed {file_count} files | "
            f"Full Repo: ~{raw_tokens} tokens -> Skeleton: ~{map_tokens} tokens ({saved}% reduction)\n"
        )
        return header + map_output

    @classmethod
    def get_outline(cls, code: str, include_stats: bool = True) -> str:
        """
        1.2 Smart File Outliner:
        Strips implementation bodies while preserving imports, constants,
        decorators, class hierarchies, method signatures, type hints, and 1-line docstrings.
        """
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return f"# SyntaxError parsing file: {e}"

        lines = []
        imports = []

        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.append(ast.unparse(node))

        if imports:
            lines.append("# --- Imports ---\n" + "\n".join(imports))

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                lines.append(cls._format_function_sig(node, indent=""))

            elif isinstance(node, ast.ClassDef):
                decorators = [f"@{ast.unparse(d)}" for d in node.decorator_list]
                bases = f"({', '.join(ast.unparse(b) for b in node.bases)})" if node.bases else ""
                class_header = "\n".join(decorators + [f"class {node.name}{bases}:"])
                class_lines = [class_header]

                doc = ast.get_docstring(node)
                if doc:
                    first_line = doc.strip().splitlines()[0]
                    class_lines.append(f'    """{first_line}"""')

                members = 0
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        class_lines.append(cls._format_function_sig(item, indent="    "))
                        members += 1
                    elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        class_lines.append(f"    {item.target.id}: {ast.unparse(item.annotation)}")
                        members += 1
                    elif isinstance(item, ast.Assign):
                        for t in item.targets:
                            if isinstance(t, ast.Name):
                                class_lines.append(f"    {t.id} = ...")
                                members += 1

                if members == 0 and not doc:
                    class_lines.append("    ...")
                lines.append("\n".join(class_lines))

            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        val_preview = ast.unparse(node.value)
                        if len(val_preview) > 50:
                            val_preview = val_preview[:47] + "..."
                        lines.append(f"{target.id} = {val_preview}")

            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                lines.append(f"{node.target.id}: {ast.unparse(node.annotation)} = ...")

        body_out = "\n\n".join(lines) if lines else "# Empty or comment-only module."
        if include_stats:
            return cls.compression_stats(code, body_out) + "\n\n" + body_out
        return body_out

    @staticmethod
    def _format_function_sig(node: ast.AST, indent: str = "") -> str:
        """Helper to format function signature with decorators, types, and 1-line docstring."""
        assert isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        decs = [f"{indent}@{ast.unparse(d)}" for d in node.decorator_list]
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        args = ast.unparse(node.args)
        returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
        doc = ast.get_docstring(node)
        line_range = f"  # L{node.lineno}-L{getattr(node, 'end_lineno', node.lineno)}"

        sig_line = f"{indent}{prefix} {node.name}({args}){returns}:{line_range}"
        if doc:
            summary = doc.strip().splitlines()[0]
            return "\n".join(decs + [sig_line, f'{indent}    """{summary}"""', f"{indent}    ..."])
        return "\n".join(decs + [sig_line.replace(f":{line_range}", f": ...{line_range}")])

    @classmethod
    def get_symbol_slice(
        cls,
        code: str,
        symbol_name: str,
        include_dependencies: bool = True
    ) -> str:
        """
        1.3 Transitive Symbol Slicer:
        Extracts the exact AST block for `symbol_name` PLUS any local helper functions,
        classes, or module constants in the same file that `symbol_name` references.
        Supports 'ClassName.method_name' or top-level 'symbol_name'.
        """
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return f"# SyntaxError: {e}"

        # Map all top-level definitions by name
        top_defs: Dict[str, ast.AST] = {}
        imports: List[ast.AST] = []

        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.append(node)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                top_defs[node.name] = node
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        top_defs[t.id] = node
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                top_defs[node.target.id] = node

        # Support ClassName.method_name slicing
        target_node: Optional[ast.AST] = None
        if "." in symbol_name:
            cls_name, method_name = symbol_name.split(".", 1)
            cls_node = top_defs.get(cls_name)
            if isinstance(cls_node, ast.ClassDef):
                for item in cls_node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == method_name:
                        target_node = item
                        break
        else:
            target_node = top_defs.get(symbol_name)

        if not target_node:
            available = ", ".join(sorted(top_defs.keys()))
            return f"# Error: Symbol '{symbol_name}' not found. Available top-level symbols: [{available}]"

        # Resolve transitive local dependencies within the same file
        resolved_order: List[str] = []
        visited: Set[str] = set()

        def resolve_deps(node: ast.AST):
            for child in ast.walk(node):
                if isinstance(child, ast.Name):
                    ref = child.id
                    if ref in top_defs and ref != symbol_name and ref not in visited:
                        visited.add(ref)
                        if include_dependencies:
                            resolve_deps(top_defs[ref])
                            resolved_order.append(ref)

        resolve_deps(target_node)

        # Filter imports to only those referenced in the slice + its dependencies
        all_referenced_names: Set[str] = set()
        nodes_to_scan = [target_node] + [top_defs[d] for d in resolved_order]
        for n in nodes_to_scan:
            for child in ast.walk(n):
                if isinstance(child, ast.Name):
                    all_referenced_names.add(child.id)
                elif isinstance(child, ast.Attribute):
                    all_referenced_names.add(child.attr)

        relevant_imports = []
        for imp in imports:
            if isinstance(imp, ast.Import):
                for alias in imp.names:
                    bound_name = alias.asname or alias.name.split(".")[0]
                    if bound_name in all_referenced_names:
                        relevant_imports.append(ast.unparse(imp))
                        break
            elif isinstance(imp, ast.ImportFrom):
                for alias in imp.names:
                    bound_name = alias.asname or alias.name
                    if bound_name == "*" or bound_name in all_referenced_names:
                        relevant_imports.append(ast.unparse(imp))
                        break

        output_parts = []
        if relevant_imports:
            output_parts.append("# --- Required Imports ---\n" + "\n".join(relevant_imports))

        if resolved_order:
            dep_blocks = []
            for dep_name in resolved_order:
                dep_node = top_defs[dep_name]
                line_info = f"# [Local Dependency: {dep_name} (L{dep_node.lineno})]"
                dep_blocks.append(f"{line_info}\n{ast.unparse(dep_node)}")
            output_parts.append("# --- Transitive Local Dependencies ---\n" + "\n\n".join(dep_blocks))

        target_line = getattr(target_node, "lineno", 1)
        target_end = getattr(target_node, "end_lineno", target_line)
        output_parts.append(
            f"# --- Target Symbol: {symbol_name} (L{target_line}-L{target_end}) ---\n"
            f"{ast.unparse(target_node)}"
        )

        final_slice = "\n\n".join(output_parts)
        return cls.compression_stats(code, final_slice) + "\n\n" + final_slice
