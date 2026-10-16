import ast
import os
import re
from typing import Any, Dict, List, Set, Tuple


class DependencyAuditor:
    """
    Phase 4.1 & 4.2: Dependency Hygiene & Orphan File Auditor.
    Reconciles requirements.txt and pyproject.toml against actual AST imports
    with full PyPI-to-import alias resolution, and detects orphaned module files.
    """

    IGNORE_DIRS = {
        ".git", "__pycache__", "venv", ".venv", "env",
        "node_modules", "build", "dist", ".pytest_cache", ".mypy_cache"
    }

    STD_LIB = {
        "abc", "argparse", "ast", "asyncio", "base64", "bisect", "builtins",
        "calendar", "collections", "concurrent", "contextlib", "contextvars",
        "copy", "csv", "ctypes", " dataclasses", "dataclasses", "datetime",
        "decimal", "difflib", "dis", "email", "enum", "errno", "faulthandler",
        "fcntl", "filecmp", "fileinput", "fnmatch", "fractions", "ftplib",
        "functools", "gc", "getopt", "getpass", "gettext", "glob", "Graphlib",
        "gzip", "hashlib", "heapq", "hmac", "html", "http", "imaplib",
        "importlib", "inspect", "io", "ipaddress", "itertools", "json",
        "keyword", "linecache", "locale", "logging", "lzma", "mailbox",
        "math", "mimetypes", "mmap", "multiprocessing", "netrc", "numbers",
        "operator", "optparse", "os", "pathlib", "pdb", "pickle", "pickletools",
        "pkgutil", "platform", "plistlib", "poplib", "posix", "pprint",
        "profile", "pstats", "pty", "pwd", "py_compile", "pyclbr", "pydoc",
        "queue", "quopri", "random", "re", "readline", "reprlib", "resource",
        "rlcompleter", "runpy", "sched", "secrets", "select", "selectors",
        "shelve", "shlex", "shutil", "signal", "site", "smtplib", "socket",
        "socketserver", "sqlite3", "ssl", "stat", "statistics", "string",
        "stringprep", "struct", "subprocess", "sys", "sysconfig", "syslog",
        "tabnanny", "tarfile", "tempfile", "termios", "test", "textwrap",
        "threading", "time", "timeit", "tkinter", "token", "tokenize",
        "tomllib", "trace", "traceback", "tracemalloc", "tty", "turtle",
        "types", "typing", "unicodedata", "unittest", "urllib", "uuid",
        "venv", "warnings", "wave", "weakref", "webbrowser", "winreg",
        "winsound", "wsgiref", "xdrlib", "xml", "xmlrpc", "zipapp",
        "zipfile", "zipimport", "zlib", "zoneinfo"
    }

    # Canonical PyPI package name (normalized with underscores) -> actual top-level import name
    PYPI_TO_IMPORT_MAP = {
        "pygithub": "github",
        "pillow": "pil",
        "scikit_learn": "sklearn",
        "beautifulsoup4": "bs4",
        "pyyaml": "yaml",
        "python_dotenv": "dotenv",
        "opencv_python": "cv2",
        "opencv_python_headless": "cv2",
        "pyjwt": "jwt",
        "pymysql": "pymysql",
        "psycopg2_binary": "psycopg2",
        "attrs": "attr",
        "google_generativeai": "google",
        "google_cloud_storage": "google",
        "pycryptodome": "crypto",
        "pyserial": "serial",
        " gitpython": "git",
        "gitpython": "git",
        "dateutil": "dateutil",
        "python_dateutil": "dateutil",
        "typing_extensions": "typing_extensions",
    }

    # Packages that act as runtime servers, plugins, or CLI runners without direct code imports
    RUNTIME_EXEMPT_PACKAGES = {
        "uvicorn", "gunicorn", "pytest", "pytest_asyncio", "pytest_cov",
        "black", "ruff", "flake8", "mypy", "isort", "pre_commit",
        "pip", "setuptools", "wheel", "twine", "build", "httptools", "uvloop"
    }

    @classmethod
    def extract_imported_packages(cls, root_dir: str) -> Set[str]:
        """Extracts normalized top-level package names imported anywhere in the project."""
        packages: Set[str] = set()

        for dirpath, dirnames, filenames in os.walk(root_dir):
            dirnames[:] = [d for d in sorted(dirnames) if d not in cls.IGNORE_DIRS]
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
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            pkg = alias.name.split(".")[0].lower().replace("-", "_")
                            packages.add(pkg)
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        pkg = node.module.split(".")[0].lower().replace("-", "_")
                        packages.add(pkg)

        return packages

    @classmethod
    def parse_declared_dependencies(cls, root_dir: str, req_file_name: str = "requirements.txt") -> Set[str]:
        """Parses declared dependencies from requirements.txt and/or pyproject.toml."""
        declared: Set[str] = set()

        # 1. Check requirements.txt
        req_path = os.path.join(root_dir, req_file_name)
        if os.path.exists(req_path):
            with open(req_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith(("#", "-r", "--", "git+")):
                        continue
                    match = re.match(r"^([a-zA-Z0-9_\-]+)", line)
                    if match:
                        declared.add(match.group(1).lower().replace("-", "_"))

        # 2. Check pyproject.toml
        pyproject_path = os.path.join(root_dir, "pyproject.toml")
        if os.path.exists(pyproject_path):
            with open(pyproject_path, "r", encoding="utf-8") as f:
                content = f.read()
            # Extract quoted dependency strings under dependencies = [...]
            dep_block = re.search(r"dependencies\s*=\s*\[(.*?)\]", content, re.DOTALL)
            if dep_block:
                for item in re.findall(r'["\']([a-zA-Z0-9_\-]+)[^"\']*["\']', dep_block.group(1)):
                    declared.add(item.lower().replace("-", "_"))

        return declared

    @classmethod
    def audit_requirements(cls, root_dir: str, req_file_name: str = "requirements.txt") -> Dict[str, Any]:
        """
        4.1 Manifest vs. AST Reconciler:
        Detects ghost dependencies (declared in manifest but never imported)
        and undeclared imports (imported in code, not in stdlib or local modules, and missing from manifest).
        """
        declared = cls.parse_declared_dependencies(root_dir, req_file_name)
        imported = cls.extract_imported_packages(root_dir)

        # Discover local package/module names so we don't flag them as undeclared 3rd-party packages
        local_modules: Set[str] = set()
        for dirpath, dirnames, filenames in os.walk(root_dir):
            dirnames[:] = [d for d in sorted(dirnames) if d not in cls.IGNORE_DIRS]
            for d in dirnames:
                local_modules.add(d.lower().replace("-", "_"))
            for f in filenames:
                if f.endswith(".py"):
                    local_modules.add(os.path.splitext(f)[0].lower().replace("-", "_"))

        ghost_dependencies: List[str] = []
        for pkg in sorted(declared):
            if pkg in cls.RUNTIME_EXEMPT_PACKAGES or pkg in cls.STD_LIB:
                continue
            mapped_import = cls.PYPI_TO_IMPORT_MAP.get(pkg, pkg)
            if mapped_import not in imported and pkg not in imported:
                ghost_dependencies.append(pkg)

        # Reverse map for checking undeclared imports
        import_to_pypi = {v: k for k, v in cls.PYPI_TO_IMPORT_MAP.items()}
        undeclared_imports: List[str] = []
        if declared:
            for imp in sorted(imported):
                if imp in cls.STD_LIB or imp in local_modules or imp.startswith("_"):
                    continue
                canonical_pypi = import_to_pypi.get(imp, imp)
                if imp not in declared and canonical_pypi not in declared:
                    undeclared_imports.append(imp)

        return {
            "declared_packages": sorted(list(declared)),
            "actually_imported": sorted(list(imported - cls.STD_LIB - local_modules)),
            "potential_ghost_dependencies": ghost_dependencies,
            "undeclared_third_party_imports": undeclared_imports,
        }

    @classmethod
    def find_orphan_files(cls, root_dir: str) -> List[str]:
        """
        4.2 Orphaned File Finder:
        Identifies Python files that are neither entrypoints/tests/configs
        nor imported by any other file in the repository.
        """
        exempt_filenames = {
            "__init__.py", "__main__.py", "setup.py", "conftest.py",
            "manage.py", "app.py", "main.py", "server.py", "mcp_server.py", "cli.py"
        }

        all_py_files: List[Tuple[str, str]] = []  # (rel_path, module_stem)
        all_imported_names: Set[str] = set()

        for dirpath, dirnames, filenames in os.walk(root_dir):
            dirnames[:] = [d for d in sorted(dirnames) if d not in cls.IGNORE_DIRS]
            for fname in sorted(filenames):
                if not fname.endswith(".py"):
                    continue
                full_path = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(full_path, root_dir)
                stem = os.path.splitext(fname)[0]
                all_py_files.append((rel_path, stem))

                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        code = f.read()
                    tree = ast.parse(code, filename=rel_path)
                except Exception:
                    continue

                # Check if file has `if __name__ == "__main__":` entrypoint block
                has_main_guard = any(
                    isinstance(n, ast.If) and "__main__" in ast.unparse(n.test)
                    for n in tree.body
                )
                if has_main_guard:
                    all_imported_names.add(stem)

                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            for part in alias.name.split("."):
                                all_imported_names.add(part)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            for part in node.module.split("."):
                                all_imported_names.add(part)
                        for alias in node.names:
                            all_imported_names.add(alias.name)

        orphans: List[str] = []
        for rel_path, stem in all_py_files:
            fname = os.path.basename(rel_path)
            if (
                fname in exempt_filenames
                or fname.startswith("test_")
                or fname.endswith("_test.py")
                or "tests/" in rel_path.replace("\\", "/")
            ):
                continue

            if stem not in all_imported_names:
                orphans.append(rel_path)

        return sorted(orphans)
