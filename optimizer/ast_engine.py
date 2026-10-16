import ast
import os
from typing import Dict, List, Optional, Set, Tuple
from optimizer.utils import IGNORE_DIRS


class ASTSymbolEngine:
    """
    Phase 1: Context Diet & AST Slicing Engine.
    Extracts dense repo maps, compact file outlines, and transitive symbol slices
    with honest token compression telemetry.
    """

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Fast heuristic token estimator (~4 chars per token for code)."""
        if not text:
            return 0
        return max(1, len(text) // 4)

    @classmethod
    def compression_stats(cls, raw_code: str, compressed_code: str) -> str:
        """Returns a single-line telemetry header showing estimated token savings."""
        raw_t = cls.estimate_tokens(raw_code)
        comp_t = cls.estimate_tokens(compressed_code)
        if comp_t >= raw_t:
            return (
                f"# [Token Diet | estimated (chars/4)] "
                f"Raw: ~{raw_t} tokens -> Output: ~{comp_t} tokens (no reduction)"
            )
        saved_pct = round((1 - (comp_t / max(1, raw_t))) * 100, 1)
        return (
            f"# [Token Diet | estimated (chars/4)] "
            f"Raw: ~{raw_t} tokens -> Compressed: ~{comp_t} tokens ({saved_pct}% saved)"
        )

    @classmethod
    def get_repo_map(cls, root_dir: str, max_files: int = 100) -> str:
        """
        1.1 Compact Repo Skeleton:
        Generates a dense, hierarchical symbol index of the repository.
        """
        if not os.path.exists(root_dir):
            return f"# Error: Directory '{root_dir}' does not exist."

        lines = [f"# Repository Skeleton Map: {os.path.abspath(root_dir)}"]
        total_raw_chars = 0
        file_count = 0
        truncated = False

        for dirpath, dirnames, filenames in os.walk(root_dir):
            dirnames[:] = [d for d in sorted(dirnames) if d not in IGNORE_DIRS]

            for fname in sorted(filenames):
                if not fname.endswith(".py"):
                    continue

                if file_count >= max_files:
                    truncated = True
                    break

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

            if truncated:
                break

        if truncated:
            lines.append(f"\n# ... truncated after {max_files} files")

        map_output = "\n".join(lines)
        raw_tokens = max(1, total_raw_chars // 4)
        map_tokens = cls.estimate_tokens(map_output)
        if map_tokens >= raw_tokens:
            reduction_str = "no reduction"
        else:
            saved = round((1 - (map_tokens / raw_tokens)) * 100, 1)
            reduction_str = f"{saved}% reduction vs reading all indexed files"

        header = (
            f"# [Repo Map Telemetry | estimated (chars/4)] Indexed {file_count} files | "
            f"Indexed Files Total: ~{raw_tokens} tokens -> Skeleton: ~{map_tokens} tokens ({reduction_str})\n"
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
        imports = cls._collect_module_imports(tree, code)

        if imports:
            lines.append("# --- Imports ---\n" + "\n".join(seg for _, seg in imports))

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
                        for t in cls._extract_assigned_names(item):
                            class_lines.append(f"    {t} = ...")
                            members += 1

                if members == 0 and not doc:
                    class_lines.append("    ...")
                lines.append("\n".join(class_lines))

            elif isinstance(node, (ast.Assign, ast.AugAssign)):
                names = cls._extract_assigned_names(node)
                val_preview = ast.unparse(node.value) if hasattr(node, "value") and node.value else "..."
                if len(val_preview) > 50:
                    val_preview = val_preview[:47] + "..."
                for name in names:
                    lines.append(f"{name} = {val_preview}")

            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                lines.append(f"{node.target.id}: {ast.unparse(node.annotation)} = ...")

        body_out = "\n\n".join(lines) if lines else "# Empty or comment-only module."
        if include_stats:
            return cls.compression_stats(code, body_out) + "\n\n" + body_out
        return body_out

    @staticmethod
    def _format_function_sig(node: ast.AST, indent: str = "") -> str:
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

    @staticmethod
    def _extract_source_segment(code_lines: List[str], node: ast.AST) -> str:
        """Extracts original source lines for a node (including decorators), preserving comments."""
        start = getattr(node, "lineno", 1)
        decs = getattr(node, "decorator_list", [])
        if decs:
            start = min(start, min(getattr(d, "lineno", start) for d in decs))
        end = getattr(node, "end_lineno", start)
        return "\n".join(code_lines[start - 1 : end])

    @staticmethod
    def _extract_assigned_names(node: ast.AST) -> List[str]:
        """Extracts all bound variable names from Assign, AnnAssign, or AugAssign (including tuple unpacking)."""
        names: List[str] = []
        targets = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]

        for t in targets:
            for child in ast.walk(t):
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                    if child.id not in names:
                        names.append(child.id)
        return names

    @classmethod
    def _collect_module_imports(cls, tree: ast.Module, code: str) -> List[Tuple[Set[str], str]]:
        """
        Collects top-level imports as well as imports inside module-level `try/except`
        or `if TYPE_CHECKING:` blocks. Returns list of (bound_names_set, source_text).
        """
        code_lines = code.splitlines()
        results: List[Tuple[Set[str], str]] = []

        def extract_bound(imp_node: ast.AST) -> Set[str]:
            bound: Set[str] = set()
            if isinstance(imp_node, ast.Import):
                for alias in imp_node.names:
                    bound.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(imp_node, ast.ImportFrom):
                for alias in imp_node.names:
                    bound.add(alias.asname or alias.name)
            return bound

        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                results.append((extract_bound(node), cls._extract_source_segment(code_lines, node)))
            elif isinstance(node, (ast.Try, ast.If)):
                bound_all: Set[str] = set()
                for child in ast.walk(node):
                    if isinstance(child, (ast.Import, ast.ImportFrom)):
                        bound_all.update(extract_bound(child))
                if bound_all:
                    results.append((bound_all, cls._extract_source_segment(code_lines, node)))

        return results

    @classmethod
    def get_symbol_slice(
        cls,
        code: str,
        symbol_name: str,
        include_dependencies: bool = True
    ) -> str:
        """
        1.3 Transitive Symbol Slicer:
        Extracts original source text for `symbol_name` PLUS transitive local dependencies
        (module constants, tuple-unpacked vars, augmented assignments, sibling class methods,
        and class attributes) and needed imports.
        """
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return f"# SyntaxError: {e}"

        code_lines = code.splitlines()

        # Map top-level definitions: name -> list of AST nodes (to support AugAssign after Assign)
        top_defs: Dict[str, List[ast.AST]] = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                top_defs.setdefault(node.name, []).append(node)
            elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                for name in cls._extract_assigned_names(node):
                    top_defs.setdefault(name, []).append(node)

        module_imports = cls._collect_module_imports(tree, code)

        # Check if slicing a class method (`ClassName.method_name`)
        target_cls_node: Optional[ast.ClassDef] = None
        target_node: Optional[ast.AST] = None

        if "." in symbol_name:
            cls_name, member_name = symbol_name.split(".", 1)
            cls_nodes = top_defs.get(cls_name, [])
            if cls_nodes and isinstance(cls_nodes[0], ast.ClassDef):
                target_cls_node = cls_nodes[0]
                for item in target_cls_node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == member_name:
                        target_node = item
                        break
                    elif isinstance(item, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                        if member_name in cls._extract_assigned_names(item):
                            target_node = item
                            break
        else:
            nodes = top_defs.get(symbol_name, [])
            if nodes:
                target_node = nodes[-1]

        if not target_node:
            available = ", ".join(sorted(top_defs.keys()))
            return f"# Error: Symbol '{symbol_name}' not found. Available top-level symbols: [{available}]"

        # If slicing a class member, also map all members inside that class
        class_defs: Dict[str, List[ast.AST]] = {}
        if target_cls_node is not None:
            for item in target_cls_node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    class_defs.setdefault(item.name, []).append(item)
                elif isinstance(item, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                    for cname in cls._extract_assigned_names(item):
                        class_defs.setdefault(cname, []).append(item)

        selected_class_nodes: List[ast.AST] = []
        selected_top_nodes: List[ast.AST] = []
        visited_class_syms: Set[str] = set()
        visited_top_syms: Set[str] = set()

        def resolve_node_deps(node: ast.AST) -> None:
            for child in ast.walk(node):
                # Check self.<attr> or cls.<attr> references when inside a class
                if (
                    target_cls_node is not None
                    and isinstance(child, ast.Attribute)
                    and isinstance(child.value, ast.Name)
                    and child.value.id in ("self", "cls")
                ):
                    attr_name = child.attr
                    if attr_name in class_defs and attr_name not in visited_class_syms:
                        visited_class_syms.add(attr_name)
                        if include_dependencies:
                            for cnode in class_defs[attr_name]:
                                resolve_node_deps(cnode)
                                if cnode not in selected_class_nodes:
                                    selected_class_nodes.append(cnode)

                elif isinstance(child, ast.Name):
                    ref = child.id
                    if ref in top_defs and ref != symbol_name and (target_cls_node is None or ref != target_cls_node.name):
                        if ref not in visited_top_syms:
                            visited_top_syms.add(ref)
                            if include_dependencies:
                                for tnode in top_defs[ref]:
                                    resolve_node_deps(tnode)
                                    if tnode not in selected_top_nodes:
                                        selected_top_nodes.append(tnode)

        if target_cls_node is not None:
            visited_class_syms.add(symbol_name.split(".", 1)[1])
            resolve_node_deps(target_node)
            if target_node not in selected_class_nodes:
                selected_class_nodes.append(target_node)
        else:
            visited_top_syms.add(symbol_name)
            resolve_node_deps(target_node)
            for tnode in top_defs.get(symbol_name, [target_node]):
                if tnode not in selected_top_nodes:
                    selected_top_nodes.append(tnode)

        # Sort selected nodes by original line number
        selected_top_nodes.sort(key=lambda n: getattr(n, "lineno", 0))
        selected_class_nodes.sort(key=lambda n: getattr(n, "lineno", 0))

        # Collect all referenced names across all selected nodes to filter imports
        all_referenced_names: Set[str] = set()
        for n in selected_top_nodes + selected_class_nodes:
            for child in ast.walk(n):
                if isinstance(child, ast.Name):
                    all_referenced_names.add(child.id)
                elif isinstance(child, ast.Attribute):
                    all_referenced_names.add(child.attr)

        relevant_imports: List[str] = []
        for bound_names, imp_src in module_imports:
            if "*" in bound_names or (bound_names & all_referenced_names):
                relevant_imports.append(imp_src)

        output_parts: List[str] = []
        if relevant_imports:
            output_parts.append("# --- Required Imports ---\n" + "\n".join(relevant_imports))

        if selected_top_nodes and target_cls_node is not None:
            dep_blocks = [cls._extract_source_segment(code_lines, n) for n in selected_top_nodes]
            output_parts.append("# --- Transitive Module Dependencies ---\n" + "\n\n".join(dep_blocks))
        elif selected_top_nodes:
            # Top-level target + its dependencies
            dep_only = [n for n in selected_top_nodes if n is not target_node]
            if dep_only:
                dep_blocks = [cls._extract_source_segment(code_lines, n) for n in dep_only]
                output_parts.append("# --- Transitive Local Dependencies ---\n" + "\n\n".join(dep_blocks))
            target_line = getattr(target_node, "lineno", 1)
            target_end = getattr(target_node, "end_lineno", target_line)
            output_parts.append(
                f"# --- Target Symbol: {symbol_name} (L{target_line}-L{target_end}) ---\n"
                f"{cls._extract_source_segment(code_lines, target_node)}"
            )

        if target_cls_node is not None:
            # Reconstruct class header from original lines up to first body item
            cls_start = target_cls_node.lineno
            first_body_line = target_cls_node.body[0].lineno if target_cls_node.body else cls_start + 1
            cls_header_lines = code_lines[cls_start - 1 : first_body_line - 1]
            if not cls_header_lines:
                cls_header_lines = [f"class {target_cls_node.name}:"]
            class_body_segments = [cls._extract_source_segment(code_lines, n) for n in selected_class_nodes]
            class_block = "\n".join(cls_header_lines) + "\n" + "\n\n".join(class_body_segments)
            target_line = getattr(target_node, "lineno", 1)
            target_end = getattr(target_node, "end_lineno", target_line)
            output_parts.append(
                f"# --- Target Symbol: {symbol_name} (L{target_line}-L{target_end}) ---\n"
                f"{class_block}"
            )

        final_slice = "\n\n".join(output_parts)
        return cls.compression_stats(code, final_slice) + "\n\n" + final_slice
