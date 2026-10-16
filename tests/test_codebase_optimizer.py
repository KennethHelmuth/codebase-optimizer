import ast
import os
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from optimizer.ast_engine import ASTSymbolEngine
from optimizer.context_pruner import ContextPruner
from optimizer.dependency_auditor import DependencyAuditor
from optimizer.health_scorer import HealthScorer
from optimizer.hotspot_scanner import HotspotScanner
from optimizer.slop_auditor import SlopAuditor


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
    assert "Error" in res_symlink and ("outside" in res_symlink.lower() or "denied" in res_symlink.lower())

    res_dir_escape = mcp_server.get_repo_map(str(tmp_path))
    assert "Error" in res_dir_escape and ("outside" in res_dir_escape.lower() or "denied" in res_dir_escape.lower())

    res_valid = mcp_server.get_file_outline(str(valid_file))
    assert "def hello() -> int:" in res_valid
