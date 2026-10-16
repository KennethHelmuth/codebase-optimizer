---
name: codebase-optimizer
description: Autonomous AST-driven code context pruner, anti-slop auditor, complexity gate, and health scorer for AI agents.
triggers:
  - "optimize codebase"
  - "clean dead code"
  - "prune tokens"
  - "compress context"
  - "audit dependencies"
  - "health score"
---

# Codebase Optimizer Agent Skill

## Purpose
AI coding agents burn tokens reading massive raw source files and frequently introduce structural rot (duplicate helper functions, dead exports, loop I/O bottlenecks, and unreferenced dependencies). This skill equips agents with a strict 4-step optimization loop and AST tools to ensure zero token waste and zero structural bloat.

---

## The Mandatory 4-Step Agent Workflow

1. **Map & Inspect (Context Diet):**
   - **Never** read a raw source file >150 lines in full.
   - Run `get_repo_map` to locate relevant files in <500 tokens.
   - Run `get_file_outline` to inspect signatures, types, line numbers, and docstrings before touching implementation logic.

2. **Slice Before Editing:**
   - Use `get_symbol_slice` to extract only the targeted class/function along with its transitive intra-file helper dependencies and filtered imports.

3. **Develop & Refactor:**
   - Implement changes cleanly within the minimal slice.
   - Avoid creating new helper functions if an existing utility already exists in the repo map.

4. **Post-Edit Verification (Health Gate):**
   - Run `get_health_scorecard` or `audit_ai_slop` to verify that no clones, dead exports, or complexity violations were introduced.
   - **Rule:** The codebase health score must remain equal to or higher than the pre-edit baseline before submitting changes.
