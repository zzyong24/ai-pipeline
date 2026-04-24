# ai-pipeline 已知技术债 / Roadmap

> 记录已识别但尚未完成的事项。AI 生成相关代码时**必须主动提醒**。
> 大部分事项来自 `HERMES_TASK.md v1.0` 的 roadmap。

---

## 高风险（🔴 建议优先处理）

| # | 问题 | 涉及文件 | 计划 |
|---|------|---------|------|
| 1 | 设计规范在仓库**外部**（`vault/space/crafted/study/langgraph-subgraph/subgraph-design-spec.md`），新成员/AI 无法获取 | — | 迁入 `.aies/spec/subgraph-design-spec.md` |
| 2 | 缺 `requirements.txt` / `pyproject.toml`，无法标准化安装 | 仓库根 | HERMES_TASK 阶段 1（任务 1.1-1.2） |
| 3 | `01-video-md/main_graph.py` 里有**硬编码的 macOS 路径**（`/Users/zyongzhu/Workbase/...`）和 Python 版本（`python3.9`） | `main_graph.py` 26-34 行 | 用 `importlib`/虚拟环境检测重写 |
| 4 | 飞书 token 混合了 env / macOS keychain 两套逻辑，非 macOS 环境会失败 | `main_graph.py` 177-220 行 | 抽成 `subgraphs/shared/notify.py`，统一走 env |

---

## 中风险（🟠 建议修复）

| # | 问题 | 涉及文件 | 计划 |
|---|------|---------|------|
| 5 | 没有 `.env.example`，新开发者不知道要配哪些环境变量 | 仓库根 | HERMES_TASK 阶段 1 任务 1.3 |
| 6 | 没有 `Makefile`，常用命令没集中 | 仓库根 | HERMES_TASK 阶段 1 任务 1.4 |
| 7 | 没有 `README.md`（顶级），项目外观很不专业 | 仓库根 | HERMES_TASK 阶段 1 |
| 8 | 3 个 SubGraph 都有 `test.py` 但未接入 `pytest`，`make test` 还没 | `subgraphs/*/test.py` | HERMES_TASK 阶段 1 任务 1.4 |
| 9 | 未接入 Langfuse，LLM 调用的 trace / cost 无法观测 | `subgraphs/shared/llm.py` | HERMES_TASK 阶段 3 |
| 10 | 未接入 LangGraph Studio 配置（`langgraph.json`） | 仓库根 | HERMES_TASK 阶段 3 |
| 11 | 没有 Pipeline MCP Server（暴露给 Hermes） | `mcp_server/` | HERMES_TASK 阶段 4 |
| 12 | `02-podcast-md` 未创建，SubGraph 复用性未被验证 | `02-podcast-md/` | HERMES_TASK 阶段 5 |

---

## 低风险（🟡 可延后）

| # | 问题 | 涉及文件 | 计划 |
|---|------|---------|------|
| 13 | `PipelineState._dispatched` 字段用下划线前缀，语义不够清晰 | `main_graph.py` | 重命名为 `dispatched_videos`（但要同步 main_graph 所有地方） |
| 14 | `print(...)` 式日志，生产环境应该用 `logging` | 所有 `.py` | 待 Langfuse 接入后，改为结构化日志 |
| 15 | 没有 ruff / mypy 配置 | `pyproject.toml` | 接入后在 CI 跑 |
| 16 | SubGraph 的 `README.md` 格式不统一，有的很完整有的很简 | `subgraphs/*/README.md` | 写一个模板 |
| 17 | `review_status.db` 是手写 SQL，没用 ORM | `main_graph.py` | 可以用 sqlite3 Row factory 包装下 |

---

## AI 提醒规则

生成以下类型代码时，AI 应主动列出本文件中相关条目：

### 当用户说「新增 SubGraph」或「重构 SubGraph」
→ 提醒 #1：设计规范在仓库外，建议先迁入 `.aies/spec/subgraph-design-spec.md`

### 当用户说「在不同机器跑」或「打包」
→ 提醒 #3：有硬编码 macOS 路径
→ 提醒 #2：缺 `requirements.txt`

### 当用户说「接入监控 / trace」
→ 提醒 #9：未接入 Langfuse
→ 提醒 #10：未接入 Studio

### 当用户说「暴露给 Hermes / MCP」
→ 提醒 #11：`mcp_server/` 尚未建设
→ 提醒设计约束：**SubGraph 不通过 MCP 暴露**（HERMES_TASK 明确禁止），只暴露 Pipeline

### 当用户改 `main_graph.py` 的通知 / 审核逻辑
→ 提醒 #4：飞书 token 加载逻辑有环境依赖

---

## 沉淀规则

每次 bug 修复后，AI 和人一起判断：

1. 通用问题 → 补 `.ai/review-checklist.md`
2. 项目特有问题 → 补本文件
3. 架构 / 设计缺口 → 更新 `.aies/spec/architecture.md`
4. 代码风格缺口 → 更新 `.aies/spec/code-style.md`
