# 架构规范（ai-pipeline · LangGraph SubGraph）

> 本项目的核心架构约束。**所有代码生成必须遵守**。
> 违反本规范的产出 **直接打回重做**。

---

## 一、架构总览

```
┌──────────────────────────────────────────────┐
│  入口层（run.py / CLI / MCP Server）          │
│  职责：参数解析、启动主 Graph                   │
├──────────────────────────────────────────────┤
│  主 Graph 层（main_graph.py）                 │
│  职责：编排 SubGraph、Pipeline 特有逻辑（HITL/通知）│
│  禁止：业务逻辑（下沉到 SubGraph）               │
├──────────────────────────────────────────────┤
│  SubGraph 层（subgraphs/{name}_subgraph/）    │
│  职责：一个业务能力（研究/转录/写书）             │
│  禁止：依赖具体 Pipeline、Pipeline 特有逻辑      │
├──────────────────────────────────────────────┤
│  Shared 层（subgraphs/shared/）               │
│  职责：LLM 调用、超时、重试等共享工具             │
│  禁止：业务逻辑                                 │
└──────────────────────────────────────────────┘
```

**依赖方向**：入口 → 主 Graph → SubGraph → Shared，**严禁逆向依赖**。

---

## 二、SubGraph 设计约束（强制）

### 2.1 标准结构（每个 SubGraph 必须包含）

```
subgraphs/{name}_subgraph/
├── __init__.py         # 仅 export: build_xxx_subgraph, XxxState
├── graph.py            # build_xxx_subgraph() 入口
├── nodes.py            # 所有 node 函数实现
├── state.py            # XxxState TypedDict 定义
├── config.py           # XxxConfig dataclass（超时、路径等）
├── test.py             # 独立测试（python -m 可跑）
└── README.md           # SubGraph 说明（State/Input/Output/Config）
```

**不允许**：
- ❌ 把 node、state、config 挤在一个文件里
- ❌ 缺 `test.py`（每个 SubGraph 必须能独立测试）
- ❌ 缺 `config.py`（硬编码超时/路径）

### 2.2 入口函数签名（强制）

```python
# graph.py
def build_xxx_subgraph(config: XxxConfig) -> CompiledStateGraph:
    builder = StateGraph(XxxState)
    # ... add nodes / edges ...
    return builder.compile()
```

- ✅ 必须通过 `config` 参数注入配置（超时、路径、阈值等）
- ✅ 返回已 `.compile()` 的 `CompiledStateGraph`
- ❌ 不要在 `build_xxx_subgraph` 里读环境变量（配置由主 Graph 注入）

### 2.3 State 独立（模式 2，强制）

每个 SubGraph 使用**独立的 State Schema**，不共享主 Graph 的 State：

```python
# state.py — ✅ 独立 State
class ResearchState(TypedDict, total=False):
    topic: str                  # 输入
    video_urls: List[str]       # 输出
    selected_videos: List[Dict] # 输出
    error: Optional[str]        # 失败信息
```

**父子 State 映射在主 Graph 的胶水 node 中手动完成**：

```python
# main_graph.py — 父子 State 映射
def node_research(state: PipelineState) -> Dict[str, Any]:
    sub_input: ResearchState = {"topic": state["topic"]}
    sub_result = _get_research_subgraph().invoke(sub_input)
    return {
        "pending_videos": sub_result.get("video_urls", []),
        "research_results": {...},
    }
```

### 2.4 SubGraph 禁止依赖主 Graph

- ❌ 不 import 任何 Pipeline 特定模块（`01-video-md/*`）
- ❌ 不假设主 Graph 的 State 结构
- ❌ 不写"这个 SubGraph 只为 video-md 服务"这类耦合代码

SubGraph 是**独立可复用组件**。如果需要 Pipeline 特定行为（如飞书通知），放在主 Graph。

---

## 三、主 Graph 编排约束（强制）

### 3.1 主 Graph 只做这些事

- ✅ 编排 SubGraph 的调用顺序
- ✅ Pipeline 特有逻辑：HITL / 审核 / 通知 / 文件输出
- ✅ fan-out 分发（只有主 Graph 知道有几个并行任务）
- ✅ 父子 State 映射

### 3.2 主 Graph 禁止

- ❌ 业务逻辑（研究/转录/写书的算法）
- ❌ LLM 调用（放 SubGraph 里）
- ❌ 工具调用（下载/转录等放 SubGraph 里）

### 3.3 fan-out 规则（LangGraph 硬约束）

**`List[Send]` 只能从 conditional edge 返回**，不能从任何 node 返回：

```python
# ✅ 正确：conditional edge 返回 List[Send]
def route_dispatcher(state):
    pending = [v for v in state["pending_videos"]
               if v not in set(state.get("_dispatched", []))]
    if not pending:
        return "write_book_node"
    return [Send("transcribe_single", {"video": v, "idx": i})
            for i, v in enumerate(pending)]

builder.add_conditional_edges("dispatcher", route_dispatcher,
                              {"write_book_node": "write_book_node"})

# ❌ 错误：node 返回 Send 会报错
def node_dispatcher(state):
    return [Send(...)]  # 运行时崩
```

### 3.4 并行结果合并（Reducer）

fan-out 后的合并必须在 State 上声明 reducer：

```python
class PipelineState(TypedDict, total=False):
    # ✅ 正确：用 Annotated + reducer 自动合并并行结果
    completed_videos: Annotated[List[Dict], lambda a, b: a + b]
    summaries: Annotated[List[Dict], lambda a, b: a + b]
    _dispatched: Annotated[List[str], lambda a, b: a + b]

    # ❌ 错误：无 reducer，并行写入会互相覆盖
    completed_videos: List[Dict]
```

### 3.5 HITL 审核规则

- ✅ 用 `raise NodeInterrupt(...)` 触发中断
- ✅ 把 `id="unique-id"` 填上（方便恢复）
- ✅ 审核状态用独立 DB 存储（如 `review_status.db`），与 LangGraph Checkpointer 分离
- ✅ 必须有超时机制（默认 1 小时 → `timeout`）

---

## 四、Checkpointer 规范（强制）

### 4.1 每个 Pipeline 有自己的 checkpoints.db

```python
CHECKPOINT_DB = PIPELINE_DIR / "checkpoints.db"  # 放在 Pipeline 目录下

_checkpointer_saver = None
def _get_checkpointer():
    global _checkpointer_saver
    if _checkpointer_saver is None:
        conn = sqlite3.connect(str(CHECKPOINT_DB), check_same_thread=False)
        _checkpointer_saver = SqliteSaver(conn)
        _checkpointer_saver.setup()
    return _checkpointer_saver
```

### 4.2 thread_id 规则

- 每次 `./run.py start` 生成新的 `thread_id`
- 支持用户指定 `--thread-id` 续跑
- `thread_id` 必须持久化到 review_status 和日志中

---

## 五、Config 注入规范（强制）

SubGraph 所有可配置项通过 `XxxConfig` dataclass 注入，不读环境变量：

```python
# ✅ 正确
@dataclass
class TranscribeConfig:
    timeout_download: int = 300
    timeout_transcribe: int = 300
    timeout_summarize: int = 120
    output_base: Path
    tools_src: Path

# 主 Graph 构造时注入
_transcribe_subgraph = build_transcribe_subgraph(TranscribeConfig(
    timeout_download=300,
    output_base=OUTPUT_TRANSCRIBE,
    tools_src=TOOLS_SRC,
))

# ❌ 错误：SubGraph 里读环境变量
# subgraphs/transcribe_subgraph/nodes.py
TIMEOUT = int(os.environ.get("TRANSCRIBE_TIMEOUT", 300))  # 禁止
```

---

## 六、上下文透传（强制）

LangGraph 的 State 本身就是上下文载体。额外注意：

- `thread_id` 必须在主 State 中显式携带（用于审核、通知、日志）
- LLM 调用通过 `subgraphs/shared/llm.py` 统一入口，trace_id 自动注入 Langfuse
- 日志记录必须带上 `[module:node_name]` 前缀（便于追踪）：
  ```python
  print(f"[main:research] ...")
  print(f"[research_subgraph:search] ...")
  ```

---

## 七、目录职责速查

| 目录 | 职责 | 禁止 |
|------|-----|-----|
| `subgraphs/shared/` | LLM 调用、超时、重试工具 | 业务逻辑 |
| `subgraphs/{name}_subgraph/` | 单一业务能力 | 依赖 Pipeline 特定模块 |
| `{NN}-{pipeline-name}/` | 完整 Pipeline | 业务算法（放 SubGraph） |
| `{NN}-{pipeline}/tools_src/` | Pipeline 特有工具源码 | 共享给其他 Pipeline（如需共享，升级到 shared） |
| `observability/` | Langfuse / Studio 集成 | 业务逻辑 |
| `mcp_server/` | 暴露 Pipeline 给 Hermes | SubGraph（不应通过 MCP 暴露 SubGraph） |

---

## 八、强制设计规范参考

项目原始设计规范（必读）：

```
vault/space/crafted/study/langgraph-subgraph/subgraph-design-spec.md
```

> ⚠️ 该文件在项目仓库**外**。如有条件应把它迁入 `.aies/spec/subgraph-design-spec.md`（已标记为待办，见 `.ai/known-issues.md`）。
