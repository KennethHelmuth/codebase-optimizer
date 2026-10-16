import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from optimizer.ast_engine import ASTSymbolEngine
from optimizer.context_pruner import ContextPruner
from optimizer.dependency_auditor import DependencyAuditor
from optimizer.health_scorer import HealthScorer
from optimizer.hotspot_scanner import HotspotScanner
from optimizer.slop_auditor import SlopAuditor


# ==============================================================================
# P0: SECURITY (mcp_server.py)
# ==============================================================================

def test_p0_path_traversal_and_symlink_escape(tmp_path, monkeypatch):
    import mcp_server

    allowed_root = tmp_path / "workspace"
    allowed_root.mkdir()
    valid_file = allowed_root / "app.py"
    valid_file.write_text("def hello() -> int:\n    return 42\n", encoding="utf-8")

    outside_secret = tmp_path / "secret.py"
    outside_secret.write_text("SECRET = 'top_secret'\n", encoding="utf-8")

    symlink_file = allowed_root / "evil_link.py"
    symlink_file.symlink_to(outside_secret)

    monkeypatch.setenv("MCP_ALLOWED_ROOT", str(allowed_root))

    traversal_target = os.path.join("..", "..", "etc", "passwd")
    res_traversal = mcp_server.get_file_outline(traversal_target)
    assert "Error" in res_traversal and ("outside" in res_traversal.lower() or "denied" in res_traversal.lower())

    res_symlink = mcp_server.get_file_outline(str(symlink_file))
    assert "Error" in res_symlink and ("outside" in res_symlink.lower() or "denied" in res_traversal.lower())

    res_dir_escape = mcp_server.get_repo_map(str(tmp_path))
    assert "Error" in res_dir_escape and ("outside" in res_dir_escape.lower() or "denied" in res_dir_escape.lower())

    res_valid = mcp_server.get_file_outline(str(valid_file))
    assert "def hello() -> int:" in res_valid


def test_p0_http_non_loopback_requires_token(monkeypatch):
    import mcp_server

    monkeypatch.delenv("MCP_TOKEN", raising=False)
    with pytest.raises((RuntimeError, SystemExit, ValueError)):
        mcp_server.validate_http_bind("0.0.0.0", "")


def test_p0_bearer_only_auth_rejects_query_token(monkeypatch):
    import mcp_server

    monkeypatch.setenv("MCP_TOKEN", "super_secret_token_123")
    app = mcp_server.create_http_app(token="super_secret_token_123")
    client = TestClient(app)

    # Query param token must be rejected
    resp_query = client.get("/mcp?token=super_secret_token_123")
    assert resp_query.status_code == 401

    # Wrong bearer token must be rejected
    resp_wrong = client.get("/mcp", headers={"Authorization": "Bearer wrong"})
    assert resp_wrong.status_code == 401

    # Health check remains open
    resp_health = client.get("/health")
    assert resp_health.status_code == 200


# ==============================================================================
# P1.1: Clone Detection (slop_auditor._ASTNormalizer)
# ==============================================================================

def test_p1_1_clone_detection_callees_and_alpha_renaming(tmp_path):
    f1 = tmp_path / "payments.py"
    f1.write_text(
        "def charge(card, amt):\n"
        "    r = card.validate(amt)\n"
        "    log(r)\n"
        "    return send_payment(r)\n\n"
        "def refund(card, amt):\n"
        "    r = card.validate(amt)\n"
        "    log(r)\n"
        "    return send_refund(r)\n",
        encoding="utf-8",
    )

    f2 = tmp_path / "orders.py"
    f2.write_text(
        "def fetch_users(db, limit):\n"
        "    rows = db.query('SELECT * FROM users', limit)\n"
        "    if not rows:\n"
        "        return []\n"
        "    return [r.id for r in rows]\n\n"
        "def delete_orders(conn, max_items):\n"
        "    items = conn.query('DELETE FROM orders', max_items)\n"
        "    if not items:\n"
        "        return []\n"
        "    return [x.id for x in items]\n",
        encoding="utf-8",
    )

    clones = SlopAuditor.find_duplicate_logic(str(tmp_path))
    clone_fn_sets = [{loc["function"] for loc in c["locations"]} for c in clones]

    # charge and refund differ in send_payment vs send_refund -> NOT clones
    assert {"charge", "refund"} not in clone_fn_sets
    # fetch_users and delete_orders differ only in local vars & literals -> ARE clones
    assert {"fetch_users", "delete_orders"} in clone_fn_sets


def test_p1_1_nested_functions_and_dunders_not_clones(tmp_path):
    f = tmp_path / "nested.py"
    f.write_text(
        "class Box:\n"
        "    def __init__(self, a, b, c):\n"
        "        self.a = a\n"
        "        self.b = b\n"
        "        self.c = c\n\n"
        "class Bag:\n"
        "    def __init__(self, x, y, z):\n"
        "        self.a = x\n"
        "        self.b = y\n"
        "        self.c = z\n\n"
        "def outer1(x):\n"
        "    def inner(y):\n"
        "        a = y + 1\n"
        "        b = a * 2\n"
        "        return b - 3\n"
        "    res = inner(x)\n"
        "    log(res)\n"
        "    return res\n",
        encoding="utf-8",
    )
    clones = SlopAuditor.find_duplicate_logic(str(tmp_path))
    for c in clones:
        names = [loc["function"] for loc in c["locations"]]
        assert "__init__" not in names


# ==============================================================================
# P1.2: Scope-Aware Dead Export Detection (slop_auditor.find_dead_exports)
# ==============================================================================

def test_p1_2_dead_exports_scope_aware_and_confidence(tmp_path):
    # b.py calls K().run() and has @budget_cache decorator
    b_py = tmp_path / "b.py"
    b_py.write_text(
        "class K:\n"
        "    def run(self):\n"
        "        return 1\n\n"
        "def caller():\n"
        "    return K().run()\n\n"
        "@budget_cache\n"
        "def cached_calc():\n"
        "    return 99\n",
        encoding="utf-8",
    )

    # c.py defines unused top-level run(), plus string-referenced plugin_entry, plus __all__ exported_fn
    c_py = tmp_path / "c.py"
    c_py.write_text(
        "__all__ = ['exported_fn']\n\n"
        "def run():\n"
        "    return 42\n\n"
        "def exported_fn():\n"
        "    return 100\n\n"
        "def plugin_entry():\n"
        "    return 'ok'\n\n"
        "def low_conf_unused():\n"
        "    return 'maybe'\n",
        encoding="utf-8",
    )

    # d.py references plugin_entry via getattr string and mentions 'low_conf_unused' in a string
    d_py = tmp_path / "d.py"
    d_py.write_text(
        "import b\n"
        "import c\n\n"
        "def main():\n"
        "    b.caller()\n"
        "    fn = getattr(c, 'plugin_entry')\n"
        "    msg = 'low_conf_unused'\n"
        "    return fn(), msg\n",
        encoding="utf-8",
    )

    dead = SlopAuditor.find_dead_exports(str(tmp_path))
    c_dead = {item["symbol"]: item for item in dead.get("c.py", [])}
    b_dead = {item["symbol"]: item for item in dead.get("b.py", [])}

    # Unused `run` in c.py must be reported even though `K().run()` exists in b.py
    assert "run" in c_dead
    assert c_dead["run"]["confidence"] == "high"

    # exported_fn is in __all__ -> NOT reported as dead
    assert "exported_fn" not in c_dead

    # cached_calc in b.py has @budget_cache (NOT a route/tool decorator) -> MUST be reported as dead
    assert "cached_calc" in b_dead

    # string constant exact match is treated as referenced (or low confidence if configured)
    assert "plugin_entry" not in c_dead


# ==============================================================================
# P1.3: AST Slicing of Class Methods (ast_engine.get_symbol_slice)
# ==============================================================================

def test_p1_3_slice_class_method_includes_siblings_class_attrs_and_module_deps():
    code = (
        "try:\n"
        "    import math\n"
        "except ImportError:\n"
        "    math = None\n\n"
        "LIMIT, UNUSED_CONST = 5, 99\n"
        "SCALE = 1\n"
        "SCALE += 2\n\n"
        "class Svc:\n"
        "    LEVEL = 2  # keep comment\n"
        "    OTHER = 10\n\n"
        "    def helper(self, x):\n"
        "        # important comment\n"
        "        return x * LIMIT + SCALE\n\n"
        "    def unused_method(self):\n"
        "        return self.OTHER\n\n"
        "    def run(self, x):\n"
        "        return self.helper(x) + self.LEVEL + int(math.pi)\n"
    )

    sliced = ASTSymbolEngine.get_symbol_slice(code, "Svc.run")
    # Must be valid Python
    parsed = ast.parse(sliced)
    assert parsed is not None

    # Must contain LIMIT, SCALE, class Svc, LEVEL, helper, run, math, and preserve comment
    assert "LIMIT" in sliced
    assert "SCALE" in sliced
    assert "class Svc:" in sliced
    assert "LEVEL = 2  # keep comment" in sliced
    assert "def helper(self, x):" in sliced
    assert "# important comment" in sliced
    assert "def run(self, x):" in sliced
    assert "import math" in sliced
    assert "unused_method" not in sliced


# ==============================================================================
# P1.4: get_repo_map max_files break bug
# ==============================================================================

def test_p1_4_get_repo_map_stops_at_max_files(tmp_path):
    for d_idx in range(4):
        d = tmp_path / f"dir_{d_idx}"
        d.mkdir()
        for f_idx in range(3):
            (d / f"mod_{f_idx}.py").write_text(f"def fn_{d_idx}_{f_idx}(): pass\n", encoding="utf-8")

    out = ASTSymbolEngine.get_repo_map(str(tmp_path), max_files=4)
    assert out.count("📄 ") == 4
    assert out.count("truncated after 4 files") == 1


# ==============================================================================
# P1.5: Honest Token Telemetry
# ==============================================================================

def test_p1_5_token_telemetry_labels_and_no_negative_reduction():
    stats_positive = ASTSymbolEngine.compression_stats("a" * 400, "a" * 40)
    assert "estimated (chars/4)" in stats_positive

    stats_negative = ASTSymbolEngine.compression_stats("short", "much_longer_output_string_here")
    assert "no reduction" in stats_negative
    assert "-" not in stats_negative.split("->")[-1]


# ==============================================================================
# P1.6: Hotspot Scanner Loop Invariance & Deduplication
# ==============================================================================

def test_p1_6_hotspot_scanner_file_io_loop_var_and_dedupe(tmp_path):
    f = tmp_path / "scanner_sample.py"
    f.write_text(
        "import re\n"
        "import requests\n\n"
        "def process_files(paths):\n"
        "    for p in paths:\n"
        "        with open(p, 'r') as fp:\n"
        "            data = fp.read()\n"
        "        with open('constant_config.json') as cfg:\n"
        "            c = cfg.read()\n"
        "        for sub in data.splitlines():\n"
        "            m = re.compile(r'abc').search(sub)\n"
        "            requests.get(f'https://example.com/{sub}')\n",
        encoding="utf-8",
    )

    hotspots = HotspotScanner.scan_loop_hotspots(str(tmp_path))
    exprs = [h["expression"] for h in hotspots]

    # open(p, 'r') depends on loop var `p` -> NOT flagged
    assert not any("open(p" in e for e in exprs)
    # open('constant_config.json') is loop-invariant -> FLAGGED
    assert any("constant_config.json" in e for e in exprs)
    # Nested loops must not duplicate the inner re.compile or requests.get
    keys = [(h["file"], h["line"], h["kind"]) for h in hotspots]
    assert len(keys) == len(set(keys))


# ==============================================================================
# P1.7: Dependency Auditor (stdlib, pyproject bracket parser, local modules)
# ==============================================================================

def test_p1_7_dependency_auditor_stdlib_and_pyproject_brackets(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[project]\n"
        "name = 'demo'\n"
        "dependencies = [\n"
        "    'httpx[http2]>=0.27; python_version>=\"3.10\"',\n"
        "    'rich>=13.0',\n"
        "]\n"
        "[project.optional-dependencies]\n"
        "dev = ['pytest>=8.0']\n",
        encoding="utf-8",
    )

    code_file = tmp_path / "app.py"
    code_file.write_text(
        "import codecs\n"
        "import configparser\n"
        "import atexit\n"
        "import bz2\n"
        "import httpx\n",
        encoding="utf-8",
    )

    # Create a nested subpackage dir named `requests` inside a deep folder that is NOT top-level
    nested_dir = tmp_path / "internal" / "deep" / "requests"
    nested_dir.mkdir(parents=True)
    (nested_dir / "helper.py").write_text("import requests\n", encoding="utf-8")

    report = DependencyAuditor.audit_requirements(str(tmp_path))
    declared = report["declared_packages"]
    assert "httpx" in declared
    assert "rich" in declared
    assert "pytest" in declared

    # codecs/configparser/atexit/bz2 must never appear as third-party
    undeclared = report["undeclared_third_party_imports"]
    for std_mod in ("codecs", "configparser", "atexit", "bz2"):
        assert std_mod not in undeclared

    # `requests` was imported and is not a top-level local module -> must be flagged undeclared
    assert "requests" in undeclared


# ==============================================================================
# P1.8: Normalized & Confidence-Weighted Health Scorer
# ==============================================================================

def test_p1_8_health_scorer_normalized_and_deduped(tmp_path):
    for i in range(5):
        (tmp_path / f"mod_{i}.py").write_text(
            f"def used_{i}(x):\n    return x + {i}\n\n"
            f"def main_{i}():\n    return used_{i}(10)\n",
            encoding="utf-8",
        )
    res = HealthScorer.calculate_health(str(tmp_path))
    assert 0 <= res["score"] <= 100
    assert len(res["prioritized_actions"]) == len(set(res["prioritized_actions"]))


# ==============================================================================
# P2: Cleanup & Diff Context Trimming
# ==============================================================================

def test_p2_cleanup_and_diff_context_trimming():
    import optimizer

    assert not hasattr(optimizer, "DeadCodeAuditor")
    assert not os.path.exists(os.path.join(os.path.dirname(optimizer.__file__), "dead_code.py"))

    diff = (
        "diff --git a/src/app.py b/src/app.py\n"
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@ -1,12 +1,12 @@\n"
        " line1\n"
        " line2\n"
        " line3\n"
        " line4\n"
        " line5\n"
        "-old_line\n"
        "+new_line\n"
        " line7\n"
        " line8\n"
        " line9\n"
        " line10\n"
        " line11\n"
    )
    compressed = ContextPruner.compress_git_diff(diff, context_lines=2)
    assert " line1" not in compressed
    assert " line4" in compressed
    assert "+new_line" in compressed
    assert " line8" in compressed
    assert " line11" not in compressed
