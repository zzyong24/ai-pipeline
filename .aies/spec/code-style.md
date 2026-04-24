# 代码风格规范（Python · LangGraph）

> 本文件定义 ai-pipeline 的代码风格。AI 生成代码必须遵循。

---

## 一、Python 基础

- **Python ≥ 3.10**（使用 `match/case`、`X | Y` 联合类型等新语法）
- **格式化**：`ruff format`（暂未接入 CI，手动执行）
- **Lint**：`ruff check`（暂未接入 CI）
- **类型检查**：推荐加类型注解，但不强制 mypy

---

## 二、命名规范

| 类型 | 规则 | 示例 |
|------|-----|------|
| 模块文件 | snake_case | `main_graph.py`, `transcribe_subgraph/` |
| 类 / TypedDict / dataclass | PascalCase | `PipelineState`, `ResearchConfig` |
| 函数 | snake_case | `build_research_subgraph`, `node_research` |
| 常量 | UPPER_SNAKE_CASE | `CHECKPOINT_DB`, `OUTPUT_BASE` |
| 私有变量 / 函数 | 前缀 `_` | `_checkpointer_saver`, `_get_research_subgraph` |
| LangGraph node 函数 | `node_{name}` 或 `{name}` | `node_research`, `node_write_book` |
| LangGraph SubGraph 入口 | `build_{name}_subgraph` | `build_research_subgraph` |
| LangGraph State | `{Name}State` | `PipelineState`, `ResearchState` |
| LangGraph Config | `{Name}Config` | `TranscribeConfig` |

---

## 三、注释规范（强制）

### 3.1 模块级 docstring（强制）

每个 `.py` 文件顶部必须有模块 docstring：

```python
"""
01-video-md 主 Graph — 只做编排
================================

职责：
  - 编排三个 SubGraph：research / transcribe / write_book
  - Pipeline 特有的 HITL 审核
  - fan-out 分发
  - 最终通知用户

业务逻辑全部在 `subgraphs/` 下，本文件只做"编排胶水"。

规范：vault/space/crafted/study/langgraph-subgraph/subgraph-design-spec.md
"""
```

### 3.2 State 字段必须有注释

```python
# ✅ 正确：按语义分组 + 含义说明
class PipelineState(TypedDict, total=False):
    # ───────────── ① Pipeline 输入 ─────────────
    topic: str              # 用户输入的主题关键词
    thread_id: str          # LangGraph thread id（用于 resume）

    # ───────────── ② 流程状态 ─────────────
    # 当前步骤。枚举值见下方 step 注释
    step: Literal["idle", "researching", "awaiting_review",
                  "transcribing", "integrating", "done", "error"]
    # 审核状态。pending=等待中 / approved=通过 / rejected=拒绝 /
    # timeout=超时 / none=跳过审核（--urls 模式）
    review_status: Literal["pending", "approved", "rejected", "timeout", "none"]
```

### 3.3 node 函数必须有 docstring 说明职责

```python
def node_send_review_request(state: PipelineState) -> Dict[str, Any]:
    """发审核请求 → 触发 Interrupt 等待用户响应。

    特殊路径：--urls 模式（review_status=="none"）时跳过审核直接进 dispatcher。
    """
    ...
```

### 3.4 复杂决策必须有注释

```python
# 这里使用单例而非每次新建：
# - SubGraph 编译成本高（几百 ms）
# - Checkpointer 连接也复用一次
# - 进程级单例足够，无并发问题
_research_subgraph = None
```

---

## 四、LangGraph 特定约束

### 4.1 State 类型定义

```python
# ✅ 正确：TypedDict + total=False + Annotated reducer
class PipelineState(TypedDict, total=False):
    topic: str
    pending_videos: Annotated[List[str], lambda a, b: a + b]  # 并行合并

# ❌ 错误：用 dataclass 或 BaseModel
@dataclass
class PipelineState: ...  # LangGraph 对 TypedDict 兼容性更好
```

### 4.2 节点函数签名

```python
# ✅ 正确：入参是 State，返回 Dict[str, Any]（部分 State 更新）
def node_research(state: PipelineState) -> Dict[str, Any]:
    return {"step": "researching", "research_results": {...}}

# ❌ 错误：返回完整 State（会覆盖其他字段）
def node_research(state: PipelineState) -> PipelineState:
    return {**state, "step": "researching"}
```

### 4.3 SubGraph 调用必须显式映射父子 State

```python
# ✅ 正确：父→子显式转换，子→父显式提取
def node_research(state: PipelineState) -> Dict[str, Any]:
    sub_input: ResearchState = {"topic": state["topic"]}   # 父→子
    sub_result = _get_research_subgraph().invoke(sub_input)
    return {
        "pending_videos": sub_result.get("video_urls", []),  # 子→父
    }

# ❌ 错误：直接把父 State 丢给 SubGraph
sub_result = _get_research_subgraph().invoke(state)  # State Schema 不对
```

### 4.4 日志前缀规范

```python
# ✅ 正确：用 [module:node] 前缀，便于追踪
print(f"[main:research] SubGraph 返回 {len(urls)} 个视频")
print(f"[main:transcribe:{idx}] 失败: {error}")
print(f"[research_subgraph:search] 搜索关键词: {kw}")
```

---

## 五、Import 规范

### 5.1 顺序

```python
# 1. future
from __future__ import annotations

# 2. 标准库
import os
import sys
import json
from pathlib import Path
from typing import TypedDict, Annotated, Dict, Any, Literal, Optional, List

# 3. sys.path 设置（仅主 Graph 入口需要）
PIPELINE_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(PIPELINE_DIR.parent))

# 4. 加载 .env（仅主 Graph 入口需要）
from dotenv import load_dotenv
load_dotenv(str(PIPELINE_DIR / ".env"))

# 5. 第三方
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Send

# 6. 项目内
from subgraphs.research_subgraph import build_research_subgraph, ResearchState
from subgraphs.research_subgraph.config import ResearchConfig
```

### 5.2 SubGraph 内部 import 禁止回指主 Graph

```python
# ❌ 禁止：SubGraph 内部
from some_pipeline_dir.main_graph import ...

# ✅ 允许：SubGraph 之间共享
from subgraphs.shared.llm import call_llm
```

---

## 六、禁止模式

### ❌ 禁止 1：魔法数字

```python
# ❌ 错误
if timeout > 300: ...

# ✅ 正确：通过 Config 注入
@dataclass
class TranscribeConfig:
    timeout_transcribe: int = 300
```

### ❌ 禁止 2：静默吞异常

```python
# ❌ 错误
try:
    sub_result = subgraph.invoke(...)
except:
    pass

# ✅ 正确：记录 + 写入 State 让主 Graph 决策
try:
    sub_result = subgraph.invoke(...)
except Exception as e:
    print(f"[main:transcribe:{idx}] SubGraph 调用异常: {e}")
    return {"failed_videos": [video], "_dispatched": [video]}
```

### ❌ 禁止 3：硬编码路径

```python
# ❌ 错误
db_path = "/Users/zyongzhu/Workbase/ai-pipeline/01-video-md/checkpoints.db"

# ✅ 正确：用 pathlib + __file__
PIPELINE_DIR = Path(__file__).parent.resolve()
CHECKPOINT_DB = PIPELINE_DIR / "checkpoints.db"
```

### ❌ 禁止 4：在 SubGraph 里读环境变量

```python
# ❌ 错误（subgraphs/transcribe_subgraph/nodes.py）
TIMEOUT = int(os.environ.get("TRANSCRIBE_TIMEOUT", 300))

# ✅ 正确：通过 Config 注入
def node_download(state, config: TranscribeConfig):
    timeout = config.timeout_download
```

### ❌ 禁止 5：裸 print 无前缀

```python
# ❌ 错误
print("开始处理")

# ✅ 正确
print(f"[main:research] 开始处理主题: {topic}")
```

### ❌ 禁止 6：主 Graph 写业务逻辑

```python
# ❌ 错误（main_graph.py 里写转录算法）
def node_transcribe_single(state):
    audio = download(state["video"])
    text = whisper_transcribe(audio)    # 业务逻辑，应在 SubGraph
    return {"text": text}

# ✅ 正确：调 SubGraph
def node_transcribe_single(sub_state):
    sub_result = _get_transcribe_subgraph().invoke(sub_state)
    return {...}
```

---

## 七、函数拆分建议

- 单个 node 函数 ≤ 40 行（超过拆到辅助函数）
- `build_xxx_subgraph` ≤ 60 行（node 实现放 `nodes.py`）
- 单行 ≤ 100 字符（Python 生态惯例）

---

## 八、类型注解

- ✅ 公开 API（`build_xxx_subgraph`, node 函数）必须加类型注解
- ✅ 入参 / 返回值注解清晰
- ⚠️ 内部函数 / 简单变量可省略
- ⚠️ `Optional[X]` 和 `X | None` 两种风格二选一，项目当前用 `Optional[X]`（保持一致）

---

## 九、测试规范

每个 SubGraph 必须有 `test.py`，满足：

1. **可独立运行**：`python -m subgraphs.{name}.test [args]`
2. **不依赖真实外部依赖**（或标明依赖）
3. **至少一个"黄金路径"用例**

```python
# subgraphs/research_subgraph/test.py
"""独立测试：python -m subgraphs.research_subgraph.test "AI Agent 趋势"
"""
if __name__ == "__main__":
    import sys
    topic = sys.argv[1] if len(sys.argv) > 1 else "AI Agent 发展趋势"
    subgraph = build_research_subgraph(ResearchConfig(timeout=120, ...))
    result = subgraph.invoke({"topic": topic})
    print(result)
```

---

## 十、关键反模式（项目血泪史）

来自 HERMES_TASK.md 和 01-video-md/readme.md 的经验教训：

1. **❌ `List[Send]` 从 node 返回** → 运行时崩溃。必须从 conditional edge 返回
2. **❌ 不用 reducer** → 并行节点结果互相覆盖。必须 `Annotated[list, lambda a,b: a+b]`
3. **❌ 多任务共享 output 目录** → 并行写入冲突。每个任务用独立 `task-{idx}/` 子目录
4. **❌ 用 MCP 暴露 SubGraph** → 大模型上下文爆炸。SubGraph 只在 Python 内调用
5. **❌ 单文件 Pipeline** → v1 的 `pipeline.py` 758 行，已归档。必须拆 SubGraph
