import ast
import hashlib
import os
from collections import defaultdict
from typing import Any, Dict, List, Set, Tuple


class _ASTNormalizer(ast.NodeTransformer):
    """
    Normalizes an AST subtree by stripping docstrings, line numbers,
    variable names, argument names, and literal values so structurally
    identical functions produce the exact same canonical hash.
    """

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self._strip_docstring(node)
        node.name = "_fn"
        node.decorator_list = []
        node.returns = None
        return self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self._strip_docstring(node)
        node.name = "_async_fn"
        node.decorator_list = []
        node.returns = None
        return self.generic_visit(node)

    def visit_arg(self, node: ast.arg) -> Any:
        node.arg = "_arg"
        node.annotation = None
        return node

    def visit_Name(self, node: ast.Name) -> Any:
        # Preserve builtin/call concepts slightly less than structure; normalize local identifiers
        node.id = "_id"
        return node

    def visit_Constant(self, node: ast.Constant) -> Any:
        if isinstance(node.value, str):
            node.value = "_str"
        elif isinstance(node.value, (int, float)):
            node.value = 0
        return node

    @staticmethod
    def _strip_docstring(node: ast.AST) -> None:
        body = getattr(node, "body", [])
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body.pop(0)


class SlopAuditor:
    """
    Phase 2: Anti-AI-Slop & Clone Auditor.
    Detects structural AST clones across files, unreferenced dead exports,
    and hollow pass-through wrapper functions created by AI coding agents.
    """

    IGNORE_DIRS = {
        ".git", "__pycache__", "venv", ".venv", "env",
        "node_modules", "build", "dist", ".pytest_cache", ".mypy_cache"
    }

    DUNDER_OR_FRAMEWORK_EXEMPT = {
        "__init__", "__str__", "__repr__", "__eq__", "__hash__",
        "__enter__", "__exit__", "__call__", "__len__", "__iter__",
        "main", "setup", "teardown", "lifespan", "dispatch"
    }

    @classmethod
    def _iter_python_files(cls, root_dir: str) -> List[Tuple[str, str, ast.Module]]:
        """Yields (full_path, rel_path, parsed_ast) for all valid Python files in root_dir."""
        parsed_files = []
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
                    tree = ast.parse(code, filename=rel_path)
                    parsed_files.append((full_path, rel_path, tree))
                except Exception:
                    continue
        return parsed_files

    @classmethod
    def find_duplicate_logic(cls, root_dir: str, min_statements: int = 3) -> List[Dict[str, Any]]:
        """
        2.1 Structural AST Clone Detector:
        Normalizes AST subtrees and hashes them to find duplicate functions across files,
        even when variable names, comments, or literals differ.
        """
        buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        for _, rel_path, tree in cls._iter_python_files(root_dir):
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # Count non-docstring statements
                    stmts = [
                        s for s in node.body
                        if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
                    ]
                    if len(stmts) < min_statements:
                        continue

                    # Deep-copy via parse/unparse and normalize
                    try:
                        cloned_node = ast.parse(ast.unparse(node)).body[0]
                        normalized = _ASTNormalizer().visit(cloned_node)
                        ast.fix_missing_locations(normalized)
                        canonical_dump = ast.dump(normalized, annotate_fields=True, include_attributes=False)
                        digest = hashlib.sha256(canonical_dump.encode("utf-8")).hexdigest()[:12]
                    except Exception:
                        continue

                    buckets[digest].append({
                        "file": rel_path,
                        "function": node.name,
                        "line": node.lineno,
                        "statements": len(stmts),
                    })

        clones = []
        for digest, occurrences in buckets.items():
            if len(occurrences) > 1:
                clones.append({
                    "ast_hash": digest,
                    "count": len(occurrences),
                    "locations": occurrences,
                })
        return clones

    @classmethod
    def find_dead_exports(cls, root_dir: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        2.2 Cross-File Dead Export Hunter:
        Builds a full AST symbol definition vs. reference graph across the repository.
        Flags top-level public functions and classes that are never referenced outside their file
        nor called internally within their own file.
        """
        files = cls._iter_python_files(root_dir)
        defined_per_file: Dict[str, List[Tuple[str, int, str]]] = defaultdict(list)
        references_per_file: Dict[str, Set[str]] = defaultdict(set)
        internal_call_counts: Dict[Tuple[str, str], int] = defaultdict(int)

        for _, rel_path, tree in files:
            # Skip test files as export origins
            is_test_file = os.path.basename(rel_path).startswith("test_") or "tests/" in rel_path

            # Collect top-level definitions
            if not is_test_file and os.path.basename(rel_path) != "__init__.py":
                for node in tree.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        if (
                            not node.name.startswith("_")
                            and node.name not in cls.DUNDER_OR_FRAMEWORK_EXEMPT
                            and not cls._has_route_or_tool_decorator(node)
                        ):
                            kind = "class" if isinstance(node, ast.ClassDef) else "function"
                            defined_per_file[rel_path].append((node.name, node.lineno, kind))

            # Collect all symbol references in this file
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    references_per_file[rel_path].add(node.id)
                    internal_call_counts[(rel_path, node.id)] += 1
                elif isinstance(node, ast.Attribute):
                    references_per_file[rel_path].add(node.attr)
                    internal_call_counts[(rel_path, node.attr)] += 1
                elif isinstance(node, ast.alias):
                    references_per_file[rel_path].add(node.name.split(".")[0])
                    if node.asname:
                        references_per_file[rel_path].add(node.asname)

        dead_report: Dict[str, List[Dict[str, Any]]] = {}
        for rel_path, defs in defined_per_file.items():
            file_dead = []
            for sym_name, lineno, kind in defs:
                used_externally = any(
                    sym_name in refs
                    for other_path, refs in references_per_file.items()
                    if other_path != rel_path
                )
                # Note: in AST walk of its own file, a function's `name` is str attribute on FunctionDef
                # so ast.Name only triggers if it is actually referenced/called inside the file!
                used_internally = internal_call_counts[(rel_path, sym_name)] > 0

                if not used_externally and not used_internally:
                    file_dead.append({
                        "symbol": sym_name,
                        "kind": kind,
                        "line": lineno,
                    })

            if file_dead:
                dead_report[rel_path] = file_dead

        return dead_report

    @staticmethod
    def _has_route_or_tool_decorator(node: ast.AST) -> bool:
        """Exempts functions decorated with @mcp.tool, @app.get, @click.command, etc."""
        decorators = getattr(node, "decorator_list", [])
        for d in decorators:
            d_str = ast.unparse(d).lower()
            if any(k in d_str for k in ("tool", "route", "get", "post", "put", "delete", "command", "fixture")):
                return True
        return False

    @classmethod
    def find_useless_wrappers(cls, root_dir: str) -> List[Dict[str, Any]]:
        """
        2.3 Pass-Through Wrapper Detector:
        Detects hollow 1-statement functions that simply return a call to another
        function forwarding the exact same arguments without transformation.
        """
        wrappers = []

        for _, rel_path, tree in cls._iter_python_files(root_dir):
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if cls._has_route_or_tool_decorator(node) or node.name in cls.DUNDER_OR_FRAMEWORK_EXEMPT:
                        continue

                    # Strip docstring
                    stmts = [
                        s for s in node.body
                        if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
                    ]
                    if len(stmts) != 1:
                        continue

                    stmt = stmts[0]
                    call_node = None
                    if isinstance(stmt, ast.Return) and stmt.value is not None:
                        val = stmt.value.value if isinstance(stmt.value, ast.Await) else stmt.value
                        if isinstance(val, ast.Call):
                            call_node = val

                    if not call_node:
                        continue

                    # Compare parameter names vs passed argument names
                    defined_args = [a.arg for a in node.args.args if a.arg not in ("self", "cls")]
                    passed_args = [
                        ast.unparse(a) for a in call_node.args
                    ] + [
                        ast.unparse(kw.value) for kw in call_node.keywords if kw.value
                    ]

                    if defined_args and defined_args == passed_args:
                        target_callee = ast.unparse(call_node.func)
                        wrappers.append({
                            "file": rel_path,
                            "wrapper_function": node.name,
                            "line": node.lineno,
                            "delegates_directly_to": target_callee,
                            "forwarded_args": defined_args,
                        })

        return wrappers

    @classmethod
    def format_slop_report(cls, root_dir: str) -> str:
        """Runs all 3 Phase-2 detectors and formats a concise markdown report for agents."""
        clones = cls.find_duplicate_logic(root_dir)
        dead = cls.find_dead_exports(root_dir)
        wrappers = cls.find_useless_wrappers(root_dir)

        sections = [f"# Phase 2: Anti-AI-Slop Audit Report (`{root_dir}`)"]

        # 1. Clones
        sections.append(f"\n## 1. Structural AST Clones ({len(clones)} groups found)")
        if not clones:
            sections.append("- Zero structural duplicate functions detected.")
        else:
            for c in clones:
                locs = ", ".join(f"`{loc['file']}:{loc['function']}()` (L{loc['line']})" for loc in c["locations"])
                sections.append(f"- **Clone Group `{c['ast_hash']}`** ({c['count']} copies): {locs}")

        # 2. Dead Exports
        total_dead = sum(len(v) for v in dead.values())
        sections.append(f"\n## 2. Unreferenced Dead Symbols ({total_dead} found)")
        if not dead:
            sections.append("- Zero dead public functions or classes detected.")
        else:
            for file, items in dead.items():
                formatted = ", ".join(f"`{i['symbol']}` ({i['kind']} L{i['line']})" for i in items)
                sections.append(f"- **{file}**: {formatted}")

        # 3. Useless Wrappers
        sections.append(f"\n## 3. Hollow Pass-Through Wrappers ({len(wrappers)} found)")
        if not wrappers:
            sections.append("- Zero hollow pass-through wrappers detected.")
        else:
            for w in wrappers:
                sections.append(
                    f"- `{w['file']}:{w['wrapper_function']}()` (L{w['line']}) "
                    f"-> directly forwards `{w['forwarded_args']}` to `{w['delegates_directly_to']}()`"
                )

        return "\n".join(sections)
