<div align="center">

# ⚡ Codebase Optimizer
### Surgical AST Context Compression & Anti-AI-Slop Engine for Coding Agents

**[English](README.md)** | **[简体中文](README.zh-CN.md)**

</div>

---

## Overview

**Codebase Optimizer** is an autonomous, AST-driven static analysis engine, Model Context Protocol (MCP) server, and Agent Skill engineered specifically for AI coding workflows (**Claude Code**, **Gemini**, **Cursor**, **OpenCode**).

Modern AI coding agents suffer from two compounding failure modes:
1. **Input Context Bloating:** Agents read entire 1,500-line raw source files just to inspect a single function, wasting 75–90% of context tokens on unrelated boilerplate and degrading reasoning precision.
2. **Output Architectural Rot ("AI Slop"):** Across multi-turn sessions, agents duplicate existing helper functions under different names, leave behind orphaned exports, create hollow pass-through wrapper functions, introduce sequential loop I/O bottlenecks, and accumulate ghost dependencies.

`codebase-optimizer` solves both problems at the Abstract Syntax Tree (AST) level—**compressing context going into the model, and eradicating structural bloat coming out.**

---

## Core Architecture & 4-Pillar Engine

### Phase 1: Context Diet & AST Slicing (`optimizer/ast_engine.py`, `optimizer/context_pruner.py`)
* **Compact Repository Skeleton (`get_repo_map`):** Indexes an entire repository into a hierarchical symbol map (`File -> Class -> Public Methods`) in under 500 tokens, achieving **85%+ token reduction** over raw file reads.
* **Smart Signature Outliner (`get_file_outline`):** Strips function bodies while preserving imports, decorators, class inheritance, type annotations, line numbers (`# L12-L48`), and 1-line docstrings.
* **Transitive Symbol Slicer (`get_symbol_slice`):** Extracts a target function or method (`ClassName.method`) **plus** all internal helper functions and module constants it transitively calls within the same file, along with filtered imports.
* **Git Diff Noise Compressor (`compress_git_diff`):** Strips lockfiles (`package-lock.json`, `poetry.lock`), minified bundles, and excessive unchanged context lines from unified diffs.

### Phase 2: Anti-AI-Slop & Clone Auditor (`optimizer/slop_auditor.py`)
* **Canonical AST Clone Detector (`find_duplicate_logic`):** Normalizes AST subtrees (stripping variable names, argument identifiers, docstrings, and literals) and computes SHA-256 structural hashes to catch duplicate functions across files even when variables are renamed.
* **Cross-File Dead Export Graph (`find_dead_exports`):** Constructs a repository-wide symbol definition vs. reference graph to identify public functions and classes with zero external or internal callers (automatically exempting framework routes and `@mcp.tool` entrypoints).
* **Pass-Through Wrapper Detector (`find_useless_wrappers`):** Identifies hollow single-statement wrapper functions that merely forward identical arguments to another function without transformation.

### Phase 3: Runtime Bottleneck & Complexity Scanner (`optimizer/hotspot_scanner.py`)
* **Loop I/O & Sequential `await` Detector (`scan_loop_hotspots`):** Walks `For`, `AsyncFor`, and `While` AST subtrees to flag sequential `await` calls (recommending `asyncio.gather`), N+1 database queries, network requests, filesystem I/O, and repeated `re.compile()` inside loops.
* **Cognitive & Cyclomatic Complexity Gate (`check_complexity`):** Computes Cyclomatic Complexity, nesting-weighted Cognitive Complexity, maximum indentation depth, and line counts per function.
* **Heavy Top-Level Import Detector (`find_heavy_imports`):** Identifies heavy libraries (`pandas`, `torch`, `playwright`, `PIL`, etc.) imported globally at module load time when they are unused or only used inside a single isolated function.

### Phase 4: Dependency Hygiene & 0–100 Health Scorer (`optimizer/dependency_auditor.py`, `optimizer/health_scorer.py`)
* **Manifest vs. AST Reconciler (`audit_requirements`):** Cross-checks both `requirements.txt` and `pyproject.toml` against actual AST imports using a built-in PyPI-to-import alias map (`PyGithub -> github`, `Pillow -> PIL`, `scikit-learn -> sklearn`, `beautifulsoup4 -> bs4`, etc.).
* **Orphaned File Finder (`find_orphan_files`):** Detects `.py` modules that are neither entrypoints/tests nor imported by any other file in the repository.
* **Deterministic 0–100 Health Scorer (`calculate_health`):** Aggregates all 4 pillars into a weighted **0–100 Codebase Health Score (`A+` to `F`)** with a prioritized remediation checklist.

---

## Project Layout

```text
codebase-optimizer/
├── optimizer/
│   ├── __init__.py
│   ├── ast_engine.py          # Phase 1: Repo skeleton map, signature outliner & transitive AST slicer
│   ├── context_pruner.py      # Phase 1: Unified Git diff noise & lockfile compressor
│   ├── slop_auditor.py        # Phase 2: Canonical AST clone hashing, dead export graph & wrapper detector
│   ├── hotspot_scanner.py     # Phase 3: Loop I/O bottlenecks, cognitive complexity & heavy import scanner
│   ├── dependency_auditor.py  # Phase 4: Manifest vs. AST import reconciler & orphan file detector
│   └── health_scorer.py       # Phase 4: Unified 0-100 Codebase Health Scorecard engine
├── skill/
│   └── SKILL.md               # Reusable Agent Skill behavioral specification
├── mcp_server.py              # FastMCP server with zero-prompt AUTO_RUN tool annotations
├── README.md                  # English documentation
├── README.zh-CN.md            # Simplified Chinese documentation
└── requirements.txt
```

---

## MCP Tools & Agent Protocol

All MCP tools are annotated with `readOnlyHint: True` and `destructiveHint: False` for seamless, zero-prompt execution in supported MCP clients.

| Tool Name | Phase | Description | Avg. Token Savings |
| :--- | :---: | :--- | :---: |
| `get_repo_map` | 1 | Generates a repository-wide AST symbol map with telemetry. | **85% – 94%** |
| `get_file_outline` | 1 | Extracts signatures, types, line numbers, and docstrings without bodies. | **70% – 88%** |
| `get_symbol_slice` | 1 | Extracts a symbol + its transitive local helper dependencies & imports. | **75% – 92%** |
| `compress_git_diff` | 1 | Strips lockfiles and unchanged boilerplate from Git patches. | **50% – 80%** |
| `audit_ai_slop` | 2 | Runs AST clone detection, dead export analysis, and wrapper checks. | Static Audit |
| `scan_runtime_hotspots` | 3 | Detects loop I/O bottlenecks, complexity violations, and heavy imports. | Static Audit |
| `audit_dependencies` | 4 | Detects ghost dependencies and orphaned files across the project. | Static Audit |
| `get_health_scorecard` | 4 | Computes the 0–100 Codebase Health Score (`A+` to `F`) & action plan. | Executive Report |

---

## Quickstart

### 1. Installation
```bash
git clone git@github.com:KennethHelmuth/codebase-optimizer.git
cd codebase-optimizer
pip install -r requirements.txt
```

### 2. Python API Usage
```python
from optimizer import ASTSymbolEngine, SlopAuditor, HotspotScanner, HealthScorer

# 1. Generate compact repository skeleton map with token telemetry
print(ASTSymbolEngine.get_repo_map("."))

# 2. Slice a target method and its transitive intra-file dependencies
with open("optimizer/ast_engine.py") as f:
    code = f.read()
print(ASTSymbolEngine.get_symbol_slice(code, "ASTSymbolEngine.get_symbol_slice"))

# 3. Generate full 0-100 Codebase Health Scorecard
print(HealthScorer.format_health_report("."))
```

### 3. Run MCP Server
```bash
python mcp_server.py
```

---

## License
MIT License © Kenneth Helmuth
