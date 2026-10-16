# Codebase Optimizer (Engine & Agent Skill)

An autonomous, AST-driven codebase optimizer and context compressor designed specifically for AI coding agents.

AI agents generate massive amounts of code, but they rarely clean up after themselves. Over time, codebases suffer from **context rot**, **dead exports**, **ghost dependencies**, and **token-bloated context ingestion**. `codebase-optimizer` gives agents surgical AST intelligence to compress context windows, trace cross-file symbols, and eliminate codebase bloat with zero hallucinations.

---

## Core Capabilities

1. **AST Context Pruner (Token Diet)**
   - Slices functions, classes, and types with their internal dependencies intact, pruning 70%+ of irrelevant file tokens.
   - Generates compact symbol outlines (signatures, docstrings, type hints) for quick agent inspection.

2. **Cross-File Dead Code & Ghost Export Hunter**
   - Traces exported functions, variables, and types across the entire repository.
   - Detects orphaned exports and functions that are defined but never referenced anywhere else.

3. **Zombie Dependency Eliminator**
   - Correlates imported modules in code against manifests (`requirements.txt`, `pyproject.toml`, `package.json`).
   - Flags unused packages inflating Docker images and CI build times.

4. **Safe Pruning & Atomic Verification**
   - Performs surgical AST deletions without breaking indentation or syntax.
   - Verifies syntax integrity before writing changes to disk.

---

## Architecture

```
codebase-optimizer/
├── optimizer/
│   ├── __init__.py
│   ├── ast_engine.py          # Python AST symbol graph & slicer
│   ├── context_pruner.py      # Signature outlines and token compression
│   ├── dead_code.py           # Cross-file export / import reference graph
│   └── dependency_auditor.py  # Manifest vs import usage reconciler
├── mcp_server.py              # FastMCP HTTP & stdio server exposing optimizer tools
├── skill/
│   └── SKILL.md               # Agent Skill specification for Claude Code / Gemini / OpenCode
├── tests/
│   └── test_optimizer.py
├── pyproject.toml
└── requirements.txt
```

---

## Available MCP Tools

| Tool | Description |
| :--- | :--- |
| `get_file_outline` | Returns compact signatures and docstrings of a file, cutting tokens by up to 85%. |
| `get_symbol_slice` | Extracts a targeted function/class and its immediate local dependencies. |
| `find_dead_exports` | Scans a directory and returns all functions/classes exported but never imported across the repo. |
| `audit_dependencies` | Detects unused dependencies listed in manifest files. |
| `prune_dead_code` | Safely removes unused symbols and validates syntax. |

---

## License
MIT © Kenneth Helmuth
