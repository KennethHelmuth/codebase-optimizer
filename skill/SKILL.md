---
name: codebase-optimizer
description: Autonomous AST-driven code context pruner, dead export cleaner, and dependency auditor.
triggers:
  - "optimize codebase"
  - "clean dead code"
  - "prune tokens"
  - "compress context"
  - "audit dependencies"
---

# Codebase Optimizer Skill

## Purpose
When working with AI coding agents across large repositories, raw file ingestion burns tokens and invites hallucinated assumptions. This skill equips agents with surgical AST tools to inspect signatures first, slice only what's needed, and audit unused code.

## Operating Rules for Agents
1. **Never read a 500+ line file in full** if you only need one method. Call `get_file_outline` first to inspect top-level signatures for ~50 tokens.
2. **Slice before editing**: Use `get_symbol_slice` to extract just the target function and its immediate imports.
3. **Audit before releasing**: Run `find_dead_exports` and `audit_dependencies` to ensure agent-generated refactors did not leave orphaned artifacts behind.
