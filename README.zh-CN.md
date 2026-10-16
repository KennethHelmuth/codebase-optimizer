<div align="center">

# Codebase Optimizer (代码库智能优化引擎)

**专为 AI 编程智能体打造的 AST 驱动型上下文瘦身、克隆检测与零冗余架构引擎**

[**English**](./README.md) | [**简体中文**](./README.zh-CN.md)

</div>

---

## 项目概述 (Overview)

现代 AI 编程智能体（如 Claude Code、Gemini、Cursor、OpenCode）在快速生成代码方面表现卓越，但在跨会话、大规模工程迭代中普遍存在两大核心痛点：

1. **上下文窗口膨胀 (输入低效)：** 智能体往往为了修改一个仅 25 行的函数而读取 1,500+ 行的完整源文件，导致 75%–90% 的 Token 预算被无关的实现细节和样板代码吞噬。
2. **跨文件架构腐化 (输出冗余)：** 由于缺乏全局符号表记忆，AI 智能体极易在不同模块中重复编写逻辑相同的工具函数（代码克隆）、在重构后遗留无人调用的死导出（Dead Exports）、生成毫无意义的透传包装函数（Pass-Through Wrappers），并在依赖清单中堆积僵尸依赖。

**Codebase Optimizer** 集成了 **FastMCP 服务端**与**智能体行为准则技能 (Agent Skill)**。它通过确定性的抽象语法树（AST）静态分析技术，强制智能体在修改代码前执行“外科手术式”精准切片读取，并在提交前执行零冗余架构校验。

---

## 核心架构与功能模块

### 第一阶段：上下文瘦身与 AST 切片引擎 (`optimizer/ast_engine.py`)
在完整保留类型签名与结构语义的前提下，将智能体的输入 Token 消耗降低 **70%–90%**。

* **仓库骨架全貌图 (`get_repo_map`)：** 在不到 500 个 Token 内生成整个代码库的紧凑层级符号索引（`文件 -> 类 -> 公共方法 -> 顶层函数`），让智能体瞬间掌握项目全局架构。
* **智能文件大纲提取 (`get_file_outline`)：** 剥离函数与方法的具体实现体，仅保留导入语句、装饰器、类继承关系、方法签名、类型注解、精确行号范围（如 `# L14-L52`）及首行文档字符串。
* **传递依赖符号切片 (`get_symbol_slice`)：** 精准提取目标函数或类方法（如 `ClassName.method`），并**自动递归追踪**并提取该符号在当前模块内调用的所有辅助函数、常量与关联类，同时智能过滤出必需的顶层导入。
* **Git Diff 降噪压缩 (`compress_git_diff`)：** 自动剔除 `package-lock.json`、`poetry.lock`、压缩产物、SVG 矢量代码以及冗长的未改动上下文行。

### 第二阶段：反 AI 冗余代码与克隆审计 (`optimizer/slop_auditor.py`)
精准捕获单文件 Linter（如 `ruff`、`eslint`）无法识别的跨文件结构性腐化。

* **AST 结构化逻辑克隆检测 (`find_duplicate_logic`)：** 基于 `ASTNormalizer` 剥离文档字符串、变量名、参数名与字面量常量，对语法树子树进行归一化并计算 SHA-256 指纹，精准揪出跨文件的 Type-1 与 Type-2 重复逻辑函数。
* **跨文件死导出猎手 (`find_dead_exports`)：** 构建全仓库符号定义与跨文件引用图谱，定位定义了但从未在其他文件中被导入或引用的公共函数与类（智能跳过入口文件与带有路由/工具装饰器的注册函数）。
* **无效透传包装器检测 (`find_useless_wrappers`)：** 识别那些不进行任何数据转换、仅机械地将参数原样转发给底层函数的空壳包装函数。

### 第三至第五阶段路线图 (持续构建中)
* **第三阶段 — 运行时性能热点与复杂度扫描器：** 基于 AST 检测循环体内的同步/异步 I/O 调用（`await`、网络请求、数据库查询）、顶层重型依赖导入以及认知复杂度超标函数。
* **第四阶段 — 依赖卫生审计与 0–100 健康度评分：** 比对 `requirements.txt` / `pyproject.toml` 与实际 AST 导入记录，清理僵尸依赖，并输出 0–100 分的代码库健康度评级（`A+` 至 `F`）。
* **第五阶段 — 远程 GitHub 仓库直连审计与完整 Skill 规范包：** 支持通过 MCP 直接审计远程 GitHub 仓库，并提供开箱即用的 `SKILL.md` 智能体工程准则。

---

## 实测基准：Token 压缩遥测输出

第一阶段的所有工具均会在输出顶部自动附上确定性的 Token 节省遥测头：

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

## 目录结构

```text
codebase-optimizer/
├── optimizer/
│   ├── __init__.py
│   ├── ast_engine.py          # 第一阶段：仓库骨架图、签名大纲与传递依赖 AST 切片
│   ├── context_pruner.py      # 第一阶段：Git Diff 降噪压缩与 Token 预算控制
│   ├── slop_auditor.py        # 第二阶段：归一化 AST 克隆指纹、跨文件死导出与透传包装检测
│   ├── dead_code.py           # 基础跨文件引用扫描器
│   └── dependency_auditor.py  # 依赖声明文件与实际 AST 导入比对器
├── skill/
│   └── SKILL.md               # 智能体技能定义与强制四步优化工作流
├── mcp_server.py              # FastMCP 服务端（预配置免确认自动执行注解）
├── requirements.txt
├── README.md                  # 英文技术文档
└── README.zh-CN.md            # 简体中文技术文档
```

---

## 快速开始 (Quickstart)

### 1. 安装依赖

```bash
gh repo clone KennethHelmuth/codebase-optimizer
cd codebase-optimizer
pip install -r requirements.txt
```

### 2. 启动 MCP 服务端

```bash
python mcp_server.py
```

所有 MCP 工具均已配置 `readOnlyHint: True` 与 `destructiveHint: False` 注解，在 Gemini Connectors 和 Claude Desktop 等客户端中可实现零弹窗无感调用。

### 3. Python API 调用示例

```python
from optimizer import ASTSymbolEngine, SlopAuditor

# 1. 生成低于 500 Token 的全仓库符号骨架图
print(ASTSymbolEngine.get_repo_map("./my_project"))

# 2. 提取特定方法及其在同文件内的传递依赖
with open("./my_project/service.py") as f:
    code = f.read()
print(ASTSymbolEngine.get_symbol_slice(code, "PaymentProcessor.charge_card"))

# 3. 执行完整的反 AI 冗余代码审计（重复逻辑、死导出、空壳包装函数）
print(SlopAuditor.format_audit_report("./my_project"))
```

---

## MCP 工具列表

| 工具名称 | 阶段 | 功能描述 |
| :--- | :---: | :--- |
| `get_repo_map` | 1 | 生成全仓库模块、类与公共函数的紧凑层级符号索引。 |
| `get_file_outline` | 1 | 剥离函数实现体，返回方法签名、类型注解、行号范围与文档摘要。 |
| `get_symbol_slice` | 1 | 提取单个目标符号及其在文件内的传递依赖项与精简导入。 |
| `compress_git_diff` | 1 | 剔除 Git Diff 中的锁文件、静态构建产物及冗长未变动上下文。 |
| `audit_ai_slop` | 2 | 执行 AST 结构化克隆检测、跨文件死导出扫描与空壳包装器审计。 |
| `find_dead_exports` | 2 | 列出所有从未在定义文件外部被导入或引用的公共类与函数。 |
| `audit_dependencies` | 4 | 比对 `requirements.txt` 与实际 AST 导入，精准标记僵尸依赖包。 |

---

## 开源协议 (License)

本项目基于 **MIT License** 开源。由 **Kenneth Helmuth** 设计与开发。
