# ai-pipeline 业务术语表

> 统一项目内术语，避免 AI 在不同位置使用不一致的命名。
> 新增术语必须登记。

---

## 一、核心概念

| 术语 | 代码命名 | 定义 | 示例 |
|------|---------|------|------|
| **SubGraph** | `build_xxx_subgraph` | 一个可复用的 LangGraph 子图，封装单一业务能力 | `research_subgraph` / `transcribe_subgraph` / `write_book_subgraph` |
| **Pipeline** | 顶级目录 `NN-xxx/` | 一个完整的内容生产流水线（编排多个 SubGraph） | `01-video-md` / `02-podcast-md` |
| **主 Graph** | `main_graph.py` | Pipeline 的编排入口，调度 SubGraph + Pipeline 特有逻辑 | `01-video-md/main_graph.py` |
| **Shared** | `subgraphs/shared/` | 跨 SubGraph 复用的工具（LLM / 超时 / 重试） | `call_llm()` / `with_timeout()` |
| **State** | `XxxState`（TypedDict） | LangGraph 节点之间传递的数据结构 | `PipelineState` / `ResearchState` |
| **Config** | `XxxConfig`（dataclass） | SubGraph 可注入的配置（超时/路径/阈值） | `TranscribeConfig(timeout_download=300, ...)` |
| **Node** | `node_xxx` 函数 | LangGraph 图中的一个节点 | `node_research` / `node_dispatcher` |
| **Edge** | `add_edge` / `add_conditional_edges` | 节点之间的连接 | — |
| **Checkpointer** | `SqliteSaver` | LangGraph 的状态持久化机制 | `checkpoints.db` |
| **Thread** | `thread_id` | 一次 Pipeline 执行的会话标识 | 用于 resume / status 查询 |

---

## 二、流程模式术语

| 术语 | 含义 | 在项目中如何体现 |
|------|------|---------------|
| **HITL** | Human-In-The-Loop，人工审核 | `send_review_request` + `NodeInterrupt` + `wait_review` |
| **Interrupt** | LangGraph 的中断机制 | `raise NodeInterrupt(...)` 触发 |
| **fan-out** | 一对多分发（并行处理多个任务） | `route_dispatcher` 返回 `List[Send]` |
| **fan-in** | 多对一合并（并行结果聚合） | `Annotated[List, lambda a,b: a+b]` reducer |
| **Send** | LangGraph 的分发原语 | `Send("node_name", {"payload": ...})` |
| **Reducer** | 并行写入的合并函数 | `lambda a, b: a + b` |
| **胶水 node** | 主 Graph 中调 SubGraph 并做父子 State 映射的 node | `node_research` / `node_transcribe_single` |

---

## 三、Pipeline 状态枚举（01-video-md）

### `step` 字段

| 值 | 含义 | 下一步 |
|----|-----|-------|
| `idle` | 初始（未使用） | → researching |
| `researching` | 正在搜索视频 | → awaiting_review |
| `awaiting_review` | 等待人工审核 | → transcribing（approve/--urls）或 done（reject/timeout） |
| `transcribing` | 正在转录视频 | → integrating |
| `integrating` | 正在生成书稿 | → done |
| `done` | 完成 | 终态 |
| `error` | 出错 | 终态（保留 error 字段） |

### `review_status` 字段

| 值 | 含义 |
|----|-----|
| `pending` | 审核中（已发通知，等待回复） |
| `approved` | 全部通过 |
| `rejected` | 全部拒绝（Pipeline 终止） |
| `timeout` | 1 小时超时（视为拒绝） |
| `none` | 跳过审核（--urls 模式） |

---

## 四、外部系统术语

| 术语 | 定义 |
|------|-----|
| **Hermes** | 我的上层调度器（非本仓库），通过 MCP 指挥 Claude Code 执行开发任务 |
| **Claude Code MCP** | Hermes 调用 Claude Code 的 MCP 通道 |
| **Pipeline MCP Server** | 待建，用于把 Pipeline 暴露给 Hermes（`mcp_server/server.py`） |
| **Langfuse** | 自部署的 LLM 可观测平台，trace/cost/eval |
| **LangGraph Studio** | 官方调试工具，开发期必开 |
| **飞书审核** | HITL 通道：主 Graph 通过飞书 bot 发审核请求 |
| **MiniMax LLM** | 当前使用的 LLM（通过 `MINIMAX_CN_API_KEY`） |

---

## 五、禁用词 / 歧义词

为避免歧义，**避免使用**：

- ❌ `graph` 单独使用 → 容易和 SubGraph / 主 Graph 混淆。请用 `subgraph` 或 `main_graph`
- ❌ `state` 单独使用 → 容易和 LangGraph State / `step` 混淆。请用 `pipeline_state` 或具体 `{Xxx}State`
- ❌ `data` / `info` / `obj` → 太泛
- ❌ `temp` / `tmp` → 说明是临时什么
- ❌ `task` 在 LangGraph 上下文中 → 容易和 `.aies/tasks/` 或 transcribe 的 task-idx 混淆，用 `sub_task` 或 `subgraph_invocation`

---

## 六、命名规则速查

| 类型 | 规则 | 示例 |
|------|-----|------|
| SubGraph 目录 | `{domain}_subgraph/` | `research_subgraph/` |
| SubGraph 入口 | `build_{domain}_subgraph` | `build_research_subgraph` |
| SubGraph State | `{Domain}State` | `ResearchState` |
| SubGraph Config | `{Domain}Config` | `ResearchConfig` |
| Pipeline 目录 | `{NN}-{slug}/`（编号+slug） | `01-video-md`, `02-podcast-md` |
| Pipeline 主 Graph | `main_graph.py`（统一文件名） | — |
| Pipeline CLI | `run.py` | — |
| 主 Graph node | `node_{name}` | `node_research`, `node_notify` |
| 日志前缀 | `[模块:node]` | `[main:research]`, `[transcribe_subgraph:download]` |
