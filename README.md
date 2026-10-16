<div align="center">

# Codebase Optimizer

**Autonomous AST-Driven Context Pruner, Clone Detector & Anti-Bloat Engine for AI Coding Agents**

[**English**](./README.md) | [**简体中文**](./README.zh-CN.md)

</div>

---

## Overview

Modern AI coding agents (Claude Code, Gemini, Cursor, OpenCode) excel at generating code rapidly, but introduce two compounding engineering problems over multi-session workflows:

1. **Context Window Bloat (Input Inefficiency):** Agents routinely ingest 1,500+ line raw source files to inspect or edit a single 25-line method, wasting 75%–90% of token budgets on unrelated implementation bodies and boilerplate.
2. **Cross-File Architectural Rot (Output Bloat):** Because agents lack a global symbol table in memory, they frequently recreate duplicate helper utilities across files, leave orphaned exports after refactors, write hollow pass-through wrapper functions, and accumulate unused manifest dependencies.

**Codebase Optimizer** is both a **FastMCP Server** and a **Behavioral Agent Skill** that equips AI agents with deterministic Abstract Syntax Tree (AST) analysis tools—enforcing surgical context reading before edits and zero-bloat verification before commits.

---

## Core Architecture & Capabilities

### Phase 1: Context Diet & AST Slicing Engine (`optimizer/ast_engine.py`)
Reduces agent input token consumption by **70%–90%** while preserving 100% of structural and type semantics.

* **Repository Skeleton Map (`get_repo_map`):** Generates a dense, hierarchical symbol index (`File -> Class -> Public Methods -> Top-level Functions`) across an entire repository in under 500 tokens.
* **Smart File Outliner (`get_file_outline`):** Strips implementation bodies from source files while retaining imports, decorators, class inheritance hierarchies, method signatures, type annotations, line numbers (`# L14-L52`), and 1-line docstrings.
* **Transitive Symbol Slicer (`get_symbol_slice`):** Extracts a target function or method (`ClassName.method`) **plus** all internal helper functions, classes, and constants within the same module that it transitively references—filtering top-level imports down to only those required by the slice.
* **Git Diff Noise Compressor (`compress_git_diff`):** Strips lockfiles (`package-lock.json`, `poetry.lock`), minified bundles, SVG blobs, and unchanged context boilerplate from unified diffs.

### Phase 2: Anti-AI-Slop & Clone Auditor (`optimizer/slop_auditor.py`)
Eliminates multi-file structural rot that single-file linters (`ruff`, `eslint`, `flake8`) cannot see.

* **Structural AST Clone Detector (`find_duplicate_logic`):** Normalizes AST subtrees by stripping docstrings, variable names, parameter names, and literal constants (`ASTNormalizer`), then computes SHA-256 fingerprints to detect Type-1 and Type-2 duplicate functions across the repository.
* **Cross-File Dead Export Hunter (`find_dead_exports`):** Constructs a repository-wide symbol definition vs. reference graph to identify public functions and classes that have zero external callers (intelligently ignoring entrypoints and decorator-registered routes/tools).
* **Pass-Through Wrapper Detector (`find_useless_wrappers`):** Identifies hollow single-statement wrapper functions that blindly forward arguments to another function without transformation.

### Phase 3–5 Roadmap (In Progress)
* **Phase 3 — Runtime Hotspot & Complexity Scanner:** AST detection for sequential `await`/network/DB calls inside loops, heavy top-level imports, and cognitive complexity violations.
* **Phase 4 — Dependency Hygiene & 0–100 Health Scorer:** Reconciles `requirements.txt` / `pyproject.toml` against actual AST imports and outputs a unified 0–100 Codebase Health Score (`A+` to `F`).
* **Phase 5 — Remote GitHub Auditing & Master Skill Package:** Direct remote GitHub repo optimization via MCP + drop-in `SKILL.md` ruleset.

---

## Benchmark: Token Reduction Telemetry

Every Phase-1 tool includes deterministic token telemetry at the top of its output:

```python
# [Token Diet] Raw: ~4,820 tokens -> Compressed: ~410 tokens (91.5% saved)

# --- Imports ---
import ast
from typing import Dict, List, Optional

class ASTSymbolEngine:
    """Phase 1: Context Diet & AST Slicing Engine."""
    @staticmethod
    def estimate_tokens(text: str) -> int: ...  # L18-L22
    @classmethod
    def get_repo_map(cls, root_dir: str, max_files: int = 100) -> str: ...  # L32-L95
    @classmethod
    def get_outline(cls, code: str, include_stats: bool = True) -> str: ...  # L98-L168
```

---

## Project Structure

```text
codebase-optimizer/
├── optimizer/
│   ├── __init__.py
│   ├── ast_engine.py          # Phase 1: Repo maps, signature outlines & transitive AST slicing
│   ├── context_pruner.py      # Phase 1: Unified diff compression & token budget filters
│   ├── slop_auditor.py        # Phase 2: Normalized AST clone hashing, dead exports & wrapper detection
│   ├── dead_code.py           # Legacy cross-file reference scanner
│   └── dependency_auditor.py  # Manifest vs. AST import reconciler
├── skill/
│   └── SKILL.md               # Agent Skill specification & mandatory workflow loop
├── mcp_server.py              # FastMCP server (pre-configured with auto-run tool annotations)
├── requirements.txt
├── README.md                  # English documentation
└── README.zh-CN.md            # Simplified Chinese documentation (简体中文文档)
```

---

## Quickstart

### 1. Installation

```bash
gh repo clone KennethHelmuth/codebase-optimizer
cd codebase-optimizer
pip install -r requirements.txt
```

### 2. Run as an MCP Server

```bash
python mcp_server.py
```

All MCP tools are annotated with `readOnlyHint: True` and `destructiveHint: False` so modern MCP clients (such as Gemini Connectors and Claude Desktop) execute codebase inspections and audits without repetitive confirmation modals.

### 3. Programmatic Python Usage

```python
from optimizer import ASTSymbolEngine, SlopAuditor

# 1. Generate a <500 token skeleton map of a repository
print(ASTSymbolEngine.get_repo_map("./my_project"))

# 2. Slice a specific method along with its local helper dependencies
with open("./my_project/service.py") as f:
    code = f.read()
print(ASTSymbolEngine.get_symbol_slice(code, "PaymentProcessor.charge_card"))

# 3. Run full Anti-AI-Slop audit (Clones, Dead Exports, Hollow Wrappers)
print(SlopAuditor.format_audit_report("./my_project"))
```

---

## MCP Tool Reference

| Tool Name | Phase | Description |
| :--- | :---: | :--- |
| `get_repo_map` | 1 | Returns a compressed hierarchical symbol map of all modules, classes, and functions. |
| `get_file_outline` | 1 | Strips function bodies and returns signatures, types, line numbers, and docstrings. |
| `get_symbol_slice` | 1 | Extracts a single symbol and its transitive in-file dependencies + filtered imports. |
| `compress_git_diff` | 1 | Removes lockfiles, generated assets, and unchanged context lines from a Git diff. |
| `audit_ai_slop` | 2 | Runs structural AST clone detection, cross-file dead export hunting, and wrapper checks. |
| `find_dead_exports` | 2 | Lists public classes and functions never imported or referenced outside their defining file. |
| `audit_dependencies` | 4 | Compares `requirements.txt` against actual AST imports to flag ghost dependencies. |

---

## License

Released under the **MIT License**. Built by **Kenneth Helmuth**.
