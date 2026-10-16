import ast
import os
from collections import defaultdict
from typing import Any, Dict, List, Set, Tuple


class HotspotScanner:
    """
    Phase 3: Runtime Bottleneck & Complexity Scanner.
    Detects sequential await/I/O calls inside loops, high cognitive & cyclomatic
    complexity functions, and heavy top-level imports that should be lazy-loaded.
    """

    IGNORE_DIRS = {
        ".git", "__pycache__", "venv", ".venv", "env",
        "node_modules", "build", "dist", ".pytest_cache", ".mypy_cache"
    }

    # Patterns indicating expensive I/O, network, DB, or regex work inside a loop
    IO_CALL_PATTERNS = {
        "requests.get", "requests.post", "requests.put", "requests.delete", "requests.request",
        "httpx.get", "httpx.post", "client.get", "client.post", "session.get", "session.post",
        "urllib.request.urlopen", "open", "os.walk", "os.listdir", "glob.glob", "pathlib.Path.glob",
        "re.compile", "re.search", "re.match", "re.findall", "re.sub",
        "cursor.execute", "session.execute", "session.query", "db.execute",
        "subprocess.run", "subprocess.Popen", "subprocess.check_output", "os.system",
        "time.sleep", "asyncio.sleep"
    }

    # Heavy libraries that slow down CLI/server cold starts if only used in a single rare function
    HEAVY_LIBRARIES = {
        "pandas", "numpy", "scipy", "sklearn", "torch", "tensorflow", "transformers",
        "matplotlib", "seaborn", "plotly", "cv2", "PIL", "playwright", "selenium",
        "boto3", "google", "openai", "anthropic", "litellm", " duckdb", "polars",
        "cryptography", "paramiko", "openpyxl", "bs4", "lxml"
    }

    @classmethod
    def _iter_python_files(cls, root_dir: str) -> List[Tuple[str, str, ast.Module]]:
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
    def scan_loop_hotspots(cls, root_dir: str) -> List[Dict[str, Any]]:
        """
        3.1 Loop I/O & Sequential Await Detector:
        Walks all For, AsyncFor, and While loops to flag:
        - Sequential `await` calls inside loops (should use asyncio.gather / TaskGroup)
        - Network HTTP calls, DB queries, file `open()`, subprocesses, or `re.compile()` inside loops
        """
        hotspots: List[Dict[str, Any]] = []

        for _, rel_path, tree in cls._iter_python_files(root_dir):
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    cls._inspect_function_loops(rel_path, node.name, node, hotspots)

        return hotspots

    @classmethod
    def _inspect_function_loops(
        cls,
        rel_path: str,
        func_name: str,
        func_node: ast.AST,
        hotspots: List[Dict[str, Any]],
    ) -> None:
        for child in ast.walk(func_node):
            if isinstance(child, (ast.For, ast.AsyncFor, ast.While)):
                loop_line = child.lineno
                # Walk inside the loop body
                for inner in ast.walk(child):
                    # 1. Check sequential `await` inside loop
                    if isinstance(inner, ast.Await):
                        awaited_expr = ast.unparse(inner.value)
                        hotspots.append({
                            "file": rel_path,
                            "function": func_name,
                            "line": getattr(inner, "lineno", loop_line),
                            "kind": "SEQUENTIAL_AWAIT_IN_LOOP",
                            "expression": f"await {awaited_expr}",
                            "recommendation": "Batch concurrent coroutines with `await asyncio.gather(*tasks)` outside the loop.",
                        })

                    # 2. Check synchronous I/O, DB, subprocess, or regex compilation calls
                    elif isinstance(inner, ast.Call):
                        call_name = cls._resolve_call_name(inner.func)
                        if not call_name:
                            continue

                        matched_io = (
                            call_name in cls.IO_CALL_PATTERNS
                            or any(call_name.endswith(f".{p.split('.')[-1]}") and p in call_name for p in cls.IO_CALL_PATTERNS)
                        )
                        if matched_io:
                            rec = "Hoist invariant calls (e.g., `re.compile`) outside the loop or batch I/O requests."
                            if "re." in call_name:
                                rec = "Pre-compile regex with `re.compile()` at module/function scope outside the loop."
                            elif "execute" in call_name or "query" in call_name:
                                rec = "N+1 Query pattern detected: use bulk query (`WHERE id IN (...)` or `executemany`)."

                            hotspots.append({
                                "file": rel_path,
                                "function": func_name,
                                "line": getattr(inner, "lineno", loop_line),
                                "kind": "LOOP_IO_BOTTLENECK",
                                "expression": ast.unparse(inner),
                                "recommendation": rec,
                            })

    @staticmethod
    def _resolve_call_name(func_expr: ast.AST) -> str:
        if isinstance(func_expr, ast.Name):
            return func_expr.id
        elif isinstance(func_expr, ast.Attribute):
            try:
                return ast.unparse(func_expr)
            except Exception:
                return func_expr.attr
        return ""

    @classmethod
    def check_complexity(
        cls,
        root_dir: str,
        max_cognitive: int = 15,
        max_cyclomatic: int = 10,
        max_nesting: int = 4,
        max_lines: int = 80,
    ) -> List[Dict[str, Any]]:
        """
        3.2 Cognitive & Cyclomatic Complexity Gate:
        Scores every function/method across:
        - Cyclomatic Complexity (branch points + 1)
        - Cognitive Complexity (branching penalized by current nesting depth)
        - Maximum Nesting Depth
        - Function Line Length
        """
        violations: List[Dict[str, Any]] = []

        for _, rel_path, tree in cls._iter_python_files(root_dir):
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    cyclomatic, cognitive, deepest_nest = cls._compute_function_complexity(node)
                    start_line = node.lineno
                    end_line = getattr(node, "end_lineno", start_line)
                    line_count = max(1, end_line - start_line + 1)

                    reasons = []
                    if cognitive > max_cognitive:
                        reasons.append(f"Cognitive={cognitive} (>{max_cognitive})")
                    if cyclomatic > max_cyclomatic:
                        reasons.append(f"Cyclomatic={cyclomatic} (>{max_cyclomatic})")
                    if deepest_nest > max_nesting:
                        reasons.append(f"NestingDepth={deepest_nest} (>{max_nesting})")
                    if line_count > max_lines:
                        reasons.append(f"Lines={line_count} (>{max_lines})")

                    if reasons:
                        violations.append({
                            "file": rel_path,
                            "function": node.name,
                            "line": start_line,
                            "lines": line_count,
                            "cyclomatic": cyclomatic,
                            "cognitive": cognitive,
                            "max_nesting": deepest_nest,
                            "reasons": reasons,
                        })

        # Sort by highest cognitive complexity first
        violations.sort(key=lambda x: x["cognitive"], reverse=True)
        return violations

    @classmethod
    def _compute_function_complexity(cls, func_node: ast.AST) -> Tuple[int, int, int]:
        """Returns (cyclomatic_score, cognitive_score, max_nesting_depth)."""
        cyclomatic = 1
        cognitive = 0
        max_depth = 0

        branch_nodes = (
            ast.If, ast.For, ast.AsyncFor, ast.While,
            ast.ExceptHandler, ast.With, ast.AsyncWith, ast.Match
        )

        def walk_depth(node: ast.AST, current_depth: int) -> None:
            nonlocal cyclomatic, cognitive, max_depth
            if current_depth > max_depth:
                max_depth = current_depth

            for child in ast.iter_child_nodes(node):
                # Do not descend into nested function definitions
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue

                if isinstance(child, branch_nodes):
                    cyclomatic += 1
                    # Cognitive complexity increases by 1 + current nesting level
                    cognitive += 1 + current_depth
                    walk_depth(child, current_depth + 1)
                elif isinstance(child, ast.BoolOp):
                    op_count = max(1, len(child.values) - 1)
                    cyclomatic += op_count
                    cognitive += op_count
                    walk_depth(child, current_depth)
                elif isinstance(child, ast.IfExp):
                    cyclomatic += 1
                    cognitive += 1 + current_depth
                    walk_depth(child, current_depth + 1)
                else:
                    walk_depth(child, current_depth)

        walk_depth(func_node, 0)
        return cyclomatic, cognitive, max_depth

    @classmethod
    def find_heavy_imports(cls, root_dir: str) -> List[Dict[str, Any]]:
        """
        3.3 Heavy Top-Level Import Detector:
        Identifies heavy packages imported at module top-level that are either:
        - Completely unused in the file (0 functions reference them), OR
        - Used inside only 1 isolated function (candidate for lazy import inside that function).
        """
        candidates: List[Dict[str, Any]] = []

        for _, rel_path, tree in cls._iter_python_files(root_dir):
            top_imports: Dict[str, Tuple[str, int]] = {}  # bound_name -> (root_pkg, lineno)

            for node in tree.body:
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        root_pkg = alias.name.split(".")[0]
                        bound = alias.asname or root_pkg
                        if root_pkg in cls.HEAVY_LIBRARIES:
                            top_imports[bound] = (root_pkg, node.lineno)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    root_pkg = node.module.split(".")[0]
                    if root_pkg in cls.HEAVY_LIBRARIES:
                        for alias in node.names:
                            bound = alias.asname or alias.name
                            top_imports[bound] = (root_pkg, node.lineno)

            if not top_imports:
                continue

            # Check how many functions in this file actually reference each heavy import
            functions = [
                n for n in tree.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            # Also check class methods
            for n in tree.body:
                if isinstance(n, ast.ClassDef):
                    for item in n.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            functions.append(item)

            for bound_name, (pkg_name, lineno) in top_imports.items():
                using_funcs = []
                for fn in functions:
                    referenced = any(
                        isinstance(c, ast.Name) and c.id == bound_name
                        for c in ast.walk(fn)
                    )
                    if referenced:
                        using_funcs.append(fn.name)

                if len(using_funcs) == 0:
                    candidates.append({
                        "file": rel_path,
                        "package": pkg_name,
                        "bound_name": bound_name,
                        "line": lineno,
                        "status": "UNUSED_HEAVY_IMPORT",
                        "recommendation": f"Remove unused top-level import `{bound_name}` ({pkg_name}).",
                    })
                elif len(using_funcs) == 1 and len(functions) > 1:
                    candidates.append({
                        "file": rel_path,
                        "package": pkg_name,
                        "bound_name": bound_name,
                        "line": lineno,
                        "status": "SINGLE_FUNCTION_HEAVY_IMPORT",
                        "used_only_in": using_funcs[0],
                        "recommendation": f"Lazy-load `{pkg_name}` inside `{using_funcs[0]}()` to speed up module startup.",
                    })

        return candidates

    @classmethod
    def format_hotspot_report(cls, root_dir: str) -> str:
        """Runs all 3 Phase-3 scanners and outputs a structured Markdown report."""
        loops = cls.scan_loop_hotspots(root_dir)
        complex_fns = cls.check_complexity(root_dir)
        heavy_imps = cls.find_heavy_imports(root_dir)

        sections = [f"# Phase 3: Runtime Bottleneck & Complexity Report (`{root_dir}`)"]

        # 1. Loop Hotspots
        sections.append(f"\n## 1. Loop I/O & Sequential Await Hotspots ({len(loops)} found)")
        if not loops:
            sections.append("- Zero loop I/O bottlenecks or sequential awaits detected.")
        else:
            for h in loops:
                sections.append(
                    f"- **[{h['kind']}]** `{h['file']}:{h['function']}()` (L{h['line']}): "
                    f"`{h['expression']}` -> *{h['recommendation']}*"
                )

        # 2. Complexity Violations
        sections.append(f"\n## 2. Cognitive & Cyclomatic Complexity Violations ({len(complex_fns)} found)")
        if not complex_fns:
            sections.append("- All functions pass cognitive, cyclomatic, and nesting thresholds.")
        else:
            for c in complex_fns:
                reasons_str = ", ".join(c["reasons"])
                sections.append(
                    f"- `{c['file']}:{c['function']}()` (L{c['line']}) -> **{reasons_str}**"
                )

        # 3. Heavy Imports
        sections.append(f"\n## 3. Heavy Top-Level Import Candidates ({len(heavy_imps)} found)")
        if not heavy_imps:
            sections.append("- Zero bloated or lazy-loadable top-level imports detected.")
        else:
            for imp in heavy_imps:
                sections.append(
                    f"- **[{imp['status']}]** `{imp['file']}` (L{imp['line']}) -> {imp['recommendation']}"
                )

        return "\n".join(sections)
