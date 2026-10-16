<div align="center">

# ⚡ Codebase Optimizer
### Surgical AST Context Compression & Anti-AI-Slop Engine for Coding Agents

**[English](#overview)** | **[简体中文](#项目概述-chinese)** | **[Architecture](#system-architecture)** | **[MCP Tools](#mcp-tools--agent-protocol)**

</div>

---

## Overview

**Codebase Optimizer** is an autonomous, AST-driven static analysis engine, Model Context Protocol (MCP) server, and Agent Skill engineered specifically for AI coding workflows (**Claude Code**, **Gemini**, **Cursor**, **OpenCode**).

Modern AI coding agents suffer from two compounding failure modes:
1. **Input Context Bloating:** Agents read entire 1,500-line raw source files just to inspect a single function, wasting 75–90% of context tokens on unrelated boilerplate and degrading reasoning precision.
2. **Output Architectural Rot ("AI Slop"):** Across multi-turn sessions, agents duplicate existing helper functions under different names, leave behind orphaned exports, create hollow pass-through wrapper functions, and introduce unreferenced dependencies.

`codebase-optimizer` solves both problems at the Abstract Syntax Tree (AST) level—**compressing context going into the model, and eradicating structural bloat coming out.**

---

## Core Pillars & Capabilities

### Phase 1: Context Diet & AST Slicing Engine (`optimizer/ast_engine.py`)
* **Compact Repository Skeleton (`get_repo_map`):** Indexes an entire repository into a hierarchical symbol map (`File -> Class -> Public Methods`) in under 500 tokens, achieving **85%+ token reduction** over raw file reads.
* **Smart Signature Outliner (`get_file_outline`):** Strips function bodies while preserving imports, decorators, class inheritance, type annotations, line numbers (`# L12-L48`), and 1-line docstrings.
* **Transitive Symbol Slicer (`get_symbol_slice`):** Extracts a target function or method (`ClassName.method`) **plus** all internal helper functions and module constants it transitively calls within the same file, along with filtered imports.
* **Git Diff Noise Compressor (`compress_git_diff`):** Strips lockfiles (`package-lock.json`, `poetry.lock`), minified bundles, and excessive unchanged context lines from unified diffs.

### Phase 2: Anti-AI-Slop & Clone Auditor (`optimizer/slop_auditor.py`)
* **Canonical AST Clone Detector (`find_duplicate_logic`):** Normalizes AST subtrees (stripping variable names, argument identifiers, docstrings, and literals) and computes SHA-256 structural hashes to catch duplicate functions across files even when variables are renamed.
* **Cross-File Dead Export Graph (`find_dead_exports`):** Constructs a repository-wide symbol definition vs. reference graph to identify public functions and classes with zero external or internal callers (automatically exempting framework routes and `@mcp.tool` entrypoints).
* **Pass-Through Wrapper Detector (`find_useless_wrappers`):** Identifies hollow single-statement wrapper functions that merely forward identical arguments to another function without transformation.

### Phase 3–5 Roadmap (In Progress)
* **Runtime Hotspot & Complexity Scanner:** Detects I/O or `await` calls inside sequential loops, heavy top-level imports, and high cognitive complexity.
* **Zombie Dependency Reconciler & 0–100 Health Scorer:** Cross-checks manifests (`requirements.txt`, `pyproject.toml`) against actual AST imports and computes a unified **Codebase Health Grade (`A+` to `F`)**.

---

## System Architecture

```text
codebase-optimizer/
├── optimizer/
│   ├── __init__.py
│   ├── ast_engine.py          # Phase 1: Repo skeleton map, signature outliner & transitive AST slicer
│   ├── context_pruner.py      # Phase 1: Unified Git diff noise & lockfile compressor
│   ├── slop_auditor.py        # Phase 2: Canonical AST clone hashing, dead export graph & wrapper detector
│   ├── dead_code.py           # Legacy directory symbol scanner
│   └── dependency_auditor.py  # Manifest vs. AST import reconciler
├── skill/
│   └── SKILL.md               # Reusable Agent Skill behavioral specification
├── mcp_server.py              # FastMCP server with zero-prompt AUTO_RUN tool annotations
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
| `audit_ai_slop` | 2 | Runs AST clone detection, dead export analysis, and wrapper checks. | N/A (Audit) |
| `find_dead_exports` | 2 | Lists public classes and functions with zero references across the repo. | N/A (Audit) |
| `audit_dependencies` | 4 | Detects declared packages in `requirements.txt` never imported in code. | N/A (Audit) |

---

<br/>

<div align="center">

# ⚡ Codebase Optimizer (代码库优化引擎)
### 面向 AI 编程智能体的 AST 级上下文压缩与反冗余代码审计引擎

</div>

---

## 项目概述 (Chinese)

**Codebase Optimizer** 是一款专为现代 AI 编程智能体（如 **Claude Code**、**Gemini**、**Cursor**、**OpenCode**）打造的自主式抽象语法树（AST）静态分析引擎、MCP（Model Context Protocol）服务器及智能体技能（Agent Skill）。

在大型代码库中，AI 编程智能体普遍面临两大核心痛点：
1. **输入上下文膨胀（Context Bloat）：** 智能体为了修改一个函数，往往会读取上千行的完整源文件，导致 75%–90% 的 Token 浪费在无关的样板代码上，不仅增加延迟与成本，还会降低模型推理精度。
2. **输出架构腐化（AI Slop / 代码冗余）：** 在多轮对话开发中，AI 极易在不同文件中重复编写逻辑相同的工具函数、遗留无人调用的废弃导出（Dead Exports）、生成毫无意义的透传包装函数（Pass-through Wrappers），以及引入未使用的幽灵依赖。

`codebase-optimizer` 从 **AST（抽象语法树）** 底层同时解决这两个问题：**在输入端对上下文进行外科手术式的精准切片压缩，在输出端自动审计并清除代码库冗余。**

---

## 核心功能模块

### 第一阶段：上下文瘦身与 AST 切片引擎 (`optimizer/ast_engine.py`)
* **仓库骨架全息图 (`get_repo_map`)：** 在 500 Token 以内生成整个代码库的层级符号索引（`文件 -> 类 -> 公共方法`），相比直接读取源文件可节省 **85% 以上** 的上下文开销。
* **智能文件大纲提取 (`get_file_outline`)：** 剥离函数具体实现体，仅保留导入语句、装饰器、类继承关系、方法签名、类型注解、行号范围（`# L12-L48`）及单行文档字符串。
* **传递依赖符号切片 (`get_symbol_slice`)：** 精准提取目标函数或类方法（支持 `ClassName.method`），并自动追踪提取其在同一文件内调用的所有局部辅助函数、常量及所需的顶部导入语句。
* **Git Diff 降噪压缩 (`compress_git_diff`)：** 自动过滤 `package-lock.json`、`poetry.lock`、压缩产物等噪音文件，精简未改动上下文。

### 第二阶段：反 AI 冗余代码与克隆审计 (`optimizer/slop_auditor.py`)
* **AST 结构化克隆检测 (`find_duplicate_logic`)：** 对 AST 子树进行规范化归约（剥离变量名、参数名、注释及字面量常量）并计算 SHA-256 结构哈希。即使 AI 修改了变量名或注释，也能精准揪出跨文件的重复逻辑。
* **跨文件死代码追踪图 (`find_dead_exports`)：** 构建全仓符号定义与引用关系图，精准定位从未被外部文件或内部逻辑调用的公共函数与类（自动豁免路由装饰器与 `@mcp.tool` 入口函数）。
* **无效透传包装器检测 (`find_useless_wrappers`)：** 识别仅包含单条 `return` 语句且原样转发参数的空壳包装函数，消除 AI 过度抽象。

### 第三至第五阶段路线图（推进中）
* **运行时性能热点与复杂度扫描器：** 检测循环体内的同步/异步 I/O 调用、高认知复杂度嵌套函数以及可延迟加载的重型顶部导入。
* **幽灵依赖清理与 0–100 健康度评分：** 交叉比对 `requirements.txt` / `pyproject.toml` 与实际 AST 导入，输出量化的**代码库健康评级（`A+` 至 `F`）**。

---

## 快速开始 (Quickstart)

### 1. 安装依赖
```bash
git clone git@github.com:KennethHelmuth/codebase-optimizer.git
cd codebase-optimizer
pip install -r requirements.txt
```

### 2. Python API 调用示例
```python
from optimizer import ASTSymbolEngine, SlopAuditor

# 1. 生成全仓极简符号骨架图（带 Token 压缩率统计）
print(ASTSymbolEngine.get_repo_map("."))

# 2. 提取单个函数及其文件内传递依赖切片
with open("optimizer/ast_engine.py") as f:
    code = f.read()
print(ASTSymbolEngine.get_symbol_slice(code, "ASTSymbolEngine.get_symbol_slice"))

# 3. 执行反 AI 冗余代码全量审计（AST 克隆 + 死代码 + 空壳包装函数）
print(SlopAuditor.format_slop_report("."))
```

### 3. 启动 MCP 服务器
```bash
python mcp_server.py
```

---

## 开源协议 (License)
MIT License © Kenneth Helmuth
