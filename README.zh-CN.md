<div align="center">

# ⚡ Codebase Optimizer (代码库优化引擎)
### 面向 AI 编程智能体的 AST 级上下文压缩与反冗余代码审计引擎

**[English](README.md)** | **[简体中文](README.zh-CN.md)**

</div>

---

## 项目概述

**Codebase Optimizer** 是一款专为现代 AI 编程智能体（如 **Claude Code**、**Gemini**、**Cursor**、**OpenCode**）打造的自主式抽象语法树（AST）静态分析引擎、MCP（Model Context Protocol）服务器及智能体技能（Agent Skill）。

在大型代码库中，AI 编程智能体普遍面临两大核心痛点：
1. **输入上下文膨胀（Context Bloat）：** 智能体为了修改单个函数，往往会读取上千行的完整源文件，导致 75%–90% 的 Token 浪费在无关的样板代码上，不仅增加延迟与成本，还会降低模型推理精度。
2. **输出架构腐化（AI Slop / 代码冗余）：** 在多轮对话开发中，AI 极易在不同文件中重复编写逻辑相同的工具函数、遗留无人调用的废弃导出（Dead Exports）、生成空壳透传包装函数（Pass-through Wrappers）、在循环内编写串行 I/O 阻塞代码，以及引入未使用的幽灵依赖。

`codebase-optimizer` 从 **AST（抽象语法树）** 底层同时解决这两个问题：**在输入端对上下文进行外科手术式的精准切片压缩，在输出端自动审计并清除代码库结构性冗余。**

---

## 四大核心架构引擎

### 第一阶段：上下文瘦身与 AST 切片引擎 (`optimizer/ast_engine.py`, `optimizer/context_pruner.py`)
* **仓库骨架全息图 (`get_repo_map`)：** 在 500 Token 以内生成整个代码库的层级符号索引（`文件 -> 类 -> 公共方法`），相比直接读取源文件可节省 **85% 以上** 的上下文开销。
* **智能文件大纲提取 (`get_file_outline`)：** 剥离函数具体实现体，仅保留导入语句、装饰器、类继承关系、方法签名、类型注解、行号范围（`# L12-L48`）及单行文档字符串。
* **传递依赖符号切片 (`get_symbol_slice`)：** 精准提取目标函数或类方法（支持 `ClassName.method`），并自动追踪提取其在同一文件内调用的所有局部辅助函数、模块常量及按需过滤的顶部导入语句。
* **Git Diff 降噪压缩 (`compress_git_diff`)：** 自动过滤 `package-lock.json`、`poetry.lock`、压缩产物等噪音文件，精简未改动上下文。

### 第二阶段：反 AI 冗余代码与克隆审计 (`optimizer/slop_auditor.py`)
* **AST 结构化克隆检测 (`find_duplicate_logic`)：** 对 AST 子树进行规范化归约（剥离变量名、参数名、注释及字面量常量）并计算 SHA-256 结构哈希。即使 AI 修改了变量名或注释，也能精准识别跨文件的重复函数逻辑。
* **跨文件死代码追踪图 (`find_dead_exports`)：** 构建全仓符号定义与引用关系图，精准定位从未被外部文件或内部逻辑调用的公共函数与类（自动豁免路由装饰器与 `@mcp.tool` 入口函数）。
* **无效透传包装器检测 (`find_useless_wrappers`)：** 识别仅包含单条 `return` 语句且原样转发参数的空壳包装函数，消除 AI 过度抽象。

### 第三阶段：运行时性能瓶颈与复杂度扫描 (`optimizer/hotspot_scanner.py`)
* **循环 I/O 与串行 `await` 热点检测 (`scan_loop_hotspots`)：** 深度遍历 `For`、`AsyncFor` 与 `While` AST 节点，精准拦截循环内的串行 `await` 调用（建议改为 `asyncio.gather`）、N+1 数据库查询、网络请求、文件读写以及重复的 `re.compile()`。
* **认知与圈复杂度门禁 (`check_complexity`)：** 计算每个函数的圈复杂度（Cyclomatic Complexity）、嵌套加权认知复杂度（Cognitive Complexity）、最大嵌套深度及代码行数。
* **重型顶部导入检测 (`find_heavy_imports`)：** 识别在模块顶部全局导入但完全未使用，或仅在单个冷门函数内部使用的重型库（如 `pandas`、`torch`、`playwright`、`PIL` 等），提示改为函数内延迟加载（Lazy Import）以提升启动速度。

### 第四阶段：依赖卫生审计与 0–100 健康度评分 (`optimizer/dependency_auditor.py`, `optimizer/health_scorer.py`)
* **清单与 AST 导入交叉比对 (`audit_requirements`)：** 同时解析 `requirements.txt` 与 `pyproject.toml`，内置完整的 PyPI 包名与导入名映射字典（如 `PyGithub -> github`、`Pillow -> PIL`、`scikit-learn -> sklearn`、`beautifulsoup4 -> bs4`），精准识别幽灵依赖与未声明的第三方依赖。
* **孤岛文件检测 (`find_orphan_files`)：** 识别既非入口脚本/测试文件，也从未被项目内任何模块导入的孤立 `.py` 文件。
* **确定性 0–100 代码库健康度评分 (`calculate_health`)：** 汇总四大维度指标，计算加权的 **0–100 代码库健康度得分与等级（`A+` 至 `F`）**，并生成按优先级排序的修复清单。

---

## 目录结构

```text
codebase-optimizer/
├── optimizer/
│   ├── __init__.py
│   ├── ast_engine.py          # 第一阶段：全仓骨架图、签名大纲提取与传递依赖 AST 切片
│   ├── context_pruner.py      # 第一阶段：Git Diff 噪音与锁文件过滤压缩
│   ├── slop_auditor.py        # 第二阶段：AST 规范化克隆哈希、死代码追踪图与空壳包装器检测
│   ├── hotspot_scanner.py     # 第三阶段：循环 I/O 瓶颈、认知复杂度门禁与重型导入扫描
│   ├── dependency_auditor.py  # 第四阶段：依赖清单交叉审计与孤岛模块检测
│   └── health_scorer.py       # 第四阶段：0-100 代码库健康度评分与修复清单生成引擎
├── skill/
│   └── SKILL.md               # 可复用的 Agent Skill 智能体行为准则规范
├── mcp_server.py              # 预配置免确认注解 (AUTO_RUN) 的 FastMCP 服务器
├── README.md                  # 英文文档 (English Documentation)
├── README.zh-CN.md            # 简体中文文档 (Simplified Chinese Documentation)
└── requirements.txt
```

---

## MCP 工具列表与智能体协议

所有 MCP 工具均已配置 `readOnlyHint: True` 与 `destructiveHint: False` 注解，在支持该协议的客户端中可实现免弹窗自动执行。

| 工具名称 | 阶段 | 功能描述 | 平均 Token 节省率 |
| :--- | :---: | :--- | :---: |
| `get_repo_map` | 1 | 生成带遥测统计的全仓 AST 符号骨架图。 | **85% – 94%** |
| `get_file_outline` | 1 | 提取函数/类签名、类型注解、行号范围与文档摘要。 | **70% – 88%** |
| `get_symbol_slice` | 1 | 提取目标符号及其文件内传递调用的辅助函数与导入。 | **75% – 92%** |
| `compress_git_diff` | 1 | 剔除 Git 补丁中的锁文件与大段未修改上下文。 | **50% – 80%** |
| `audit_ai_slop` | 2 | 执行 AST 克隆检测、死代码分析与空壳包装函数审计。 | 静态审计 |
| `scan_runtime_hotspots` | 3 | 扫描循环内 I/O 阻塞、高复杂度函数与重型顶部导入。 | 静态审计 |
| `audit_dependencies` | 4 | 检测未使用的幽灵依赖、未声明依赖及孤岛文件。 | 静态审计 |
| `get_health_scorecard` | 4 | 计算 0–100 代码库健康度评分（`A+` 至 `F`）及修复清单。 | 综合报告 |

---

## 快速开始

### 1. 安装依赖
```bash
git clone git@github.com:KennethHelmuth/codebase-optimizer.git
cd codebase-optimizer
pip install -r requirements.txt
```

### 2. Python API 调用示例
```python
from optimizer import ASTSymbolEngine, SlopAuditor, HotspotScanner, HealthScorer

# 1. 生成全仓极简符号骨架图（带 Token 压缩率统计）
print(ASTSymbolEngine.get_repo_map("."))

# 2. 提取单个方法及其文件内传递依赖切片
with open("optimizer/ast_engine.py") as f:
    code = f.read()
print(ASTSymbolEngine.get_symbol_slice(code, "ASTSymbolEngine.get_symbol_slice"))

# 3. 输出 0-100 代码库健康度评分报告与优先修复建议
print(HealthScorer.format_health_report("."))
```

### 3. 启动 MCP 服务器
```bash
python mcp_server.py
```

---

## 开源协议
MIT License © Kenneth Helmuth
