# PRD：接入 Langfuse 可观测

> 任务 ID：`04-24-langfuse-integration`
> 优先级：P1
> 目标：让 ai-pipeline 每一次 LLM 调用、每一个 SubGraph 执行都可以在 Langfuse UI 中追踪，看到耗时、token 消耗、中间输出、错误。

---

## 一、现状与问题

- `subgraphs/shared/llm.py` 直接用 `requests` 裸调 MiniMax HTTP API，没有任何 trace
- `main_graph.py` 调用各 SubGraph 时没有 callback 机制
- 出了问题只能翻 print 日志，不知道哪个 LLM 调用慢、花了多少 token
- 没有跨 session 的历史对比

---

## 二、目标状态

跑一次 `./run.py start "AI Agent"`，在 Langfuse UI 里能看到：

```
trace: video-md-pipeline / thread_id=xxx
  ├── span: research_subgraph
  │     └── generation: llm_minimax (prompt, response, tokens, latency)
  ├── span: transcribe_single[0]
  │     └── generation: llm_minimax (summarize)
  ├── span: transcribe_single[1]
  │     └── generation: llm_minimax (summarize)
  └── span: write_book_subgraph
        ├── generation: llm_minimax (aggregate)
        └── generation: llm_minimax (write)
```

---

## 三、技术方案

### 3.1 核心思路

**不用 LangChain callback 机制**（当前 llm.py 是裸 requests，不是 LangChain 对象），改用 **Langfuse Python SDK 手动埋点**：

```
trace（整个 Pipeline run）
  └── span（SubGraph 级别）
        └── generation（llm_minimax 每次调用）
```

### 3.2 新增文件：`subgraphs/shared/observability.py`

```python
# subgraphs/shared/observability.py

from contextlib import contextmanager
from typing import Optional

def get_langfuse():
    """懒加载 Langfuse 客户端。未配置时返回 None，不阻塞运行。"""
    try:
        import os
        if not os.environ.get("LANGFUSE_PUBLIC_KEY"):
            return None
        from langfuse import Langfuse
        return Langfuse()   # 从环境变量自动读 keys
    except ImportError:
        return None

def create_trace(name: str, session_id: str, metadata: dict = None):
    """创建顶层 trace（Pipeline 级别）。"""
    lf = get_langfuse()
    if lf is None:
        return None
    return lf.trace(name=name, session_id=session_id, metadata=metadata or {})

@contextmanager
def span(trace_or_span, name: str, metadata: dict = None):
    """SubGraph 级别 span 上下文管理器。"""
    if trace_or_span is None:
        yield None
        return
    s = trace_or_span.span(name=name, metadata=metadata or {})
    try:
        yield s
        s.end()
    except Exception as e:
        s.end(status_message=str(e), level="ERROR")
        raise
```

### 3.3 改造 `subgraphs/shared/llm.py`

在 `llm_minimax()` 里加 generation 埋点：

```python
def llm_minimax(prompt: str, model: str = "MiniMax-M2", timeout: int = 120,
                trace_span=None,        # ← 新增参数
                generation_name: str = "llm_minimax") -> str:
    """
    新增参数：
      trace_span: 由调用方传入的 Langfuse span，为 None 时静默跳过
      generation_name: generation 标识名，方便在 UI 区分
    """
    # ... 原有逻辑 ...

    # Langfuse generation 埋点
    gen = None
    if trace_span is not None:
        try:
            gen = trace_span.generation(
                name=generation_name,
                model=model,
                input=prompt[:2000],   # 截断，避免太大
            )
        except Exception:
            pass

    try:
        # ... 调 API ...
        result = ...

        if gen:
            gen.end(output=result[:2000], usage={"total_tokens": ...})
        return result

    except Exception as e:
        if gen:
            gen.end(status_message=str(e), level="ERROR")
        raise
```

**关键设计**：`trace_span=None` 时完全静默，不影响现有调用方，向后兼容。

### 3.4 改造各 SubGraph nodes.py

以 `research_subgraph/nodes.py` 为例，在 `make_research_node` 工厂里接收 span：

```python
def make_research_node(config: ResearchConfig):
    def research_node(state: ResearchState) -> Dict[str, Any]:
        # 从 State 取 trace_span（主 Graph 注入）
        trace_span = state.get("_trace_span")

        raw = llm_minimax(
            prompt,
            trace_span=trace_span,
            generation_name="research/search"
        )
        ...
```

`_trace_span` 以 `_` 开头，表示 Pipeline 内部透传字段，不是业务数据。

### 3.5 改造 `main_graph.py`

在 `PipelineState` 里加透传字段，在 Pipeline 入口创建 trace：

```python
class PipelineState(TypedDict, total=False):
    # ... 原有字段 ...
    _trace_span: Optional[Any]   # Langfuse trace 对象，透传给 SubGraph

# get_app() 返回的 graph 调用时：
def run_pipeline(topic: str, thread_id: str):
    from subgraphs.shared.observability import create_trace

    trace = create_trace(
        name="video-md-pipeline",
        session_id=thread_id,
        metadata={"topic": topic}
    )

    initial_state = {
        "topic": topic,
        "thread_id": thread_id,
        "_trace_span": trace,    # ← 注入
        ...
    }
    get_app().invoke(initial_state, config={"configurable": {"thread_id": thread_id}})

    if trace:
        trace.update(status="completed")
```

### 3.6 新增文件：`observability/langfuse_setup.md`

Docker Compose 自部署指南：
- `git clone https://github.com/langfuse/langfuse && cd langfuse`
- `docker compose up -d`
- 访问 `localhost:3000` 初始化账号
- 创建项目 → 拿到 public_key / secret_key
- 写入 `01-video-md/.env`

### 3.7 环境变量（新增到 `.env.example`）

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-xxx
LANGFUSE_SECRET_KEY=sk-lf-xxx
LANGFUSE_HOST=http://localhost:3000   # 自部署地址
```

---

## 四、改动文件清单

| 文件 | 改动类型 | 说明 |
|---|---|---|
| `subgraphs/shared/observability.py` | 新增 | Langfuse 封装，懒加载，None 安全 |
| `subgraphs/shared/llm.py` | 修改 | 新增 `trace_span` 可选参数 |
| `subgraphs/research_subgraph/nodes.py` | 修改 | 从 State 取 `_trace_span`，传给 llm_minimax |
| `subgraphs/transcribe_subgraph/nodes.py` | 修改 | 同上（summarize node） |
| `subgraphs/write_book_subgraph/nodes.py` | 修改 | 同上（aggregate + write node） |
| `01-video-md/main_graph.py` | 修改 | PipelineState 加 `_trace_span`，run 入口创建 trace |
| `01-video-md/run.py` | 修改 | 调用新的 run_pipeline() 接口 |
| `observability/langfuse_setup.md` | 新增 | 自部署指南 |
| `.env.example` | 新增 | Langfuse 环境变量模板 |
| `requirements.txt` | 修改 | 加 `langfuse>=2.0.0` |

---

## 五、验收标准

- [ ] 未配置 `LANGFUSE_PUBLIC_KEY` 时，Pipeline 正常跑通，无任何报错
- [ ] 配置 Langfuse 后跑一次 Pipeline，UI 中出现对应 trace
- [ ] trace 下可看到 research / transcribe×N / write_book 各层级 span
- [ ] 每个 LLM 调用有 generation 记录（prompt 摘要、模型名、耗时）
- [ ] 某次 LLM 失败时，generation 显示 ERROR 状态
- [ ] 改动不破坏现有三个 SubGraph 的独立 test.py
