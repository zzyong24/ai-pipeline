"""transcribe_subgraph 构图函数。

使用：
    from subgraphs.transcribe_subgraph import build_transcribe_subgraph
    subgraph = build_transcribe_subgraph(config)
    result = subgraph.invoke({"video_url": "...", "task_idx": 0})

主 Graph 嵌入时（模式 2 独立 Schema）：
    main.add_node("transcribe_single", build_transcribe_subgraph(config))
    # 配合 map 函数在父子 State 之间转换
"""
from __future__ import annotations
from typing import Optional

from langgraph.graph import StateGraph, START, END

from .state import TranscribeState
from .nodes import make_download_node, make_transcribe_node, make_summarize_node
from .config import TranscribeConfig


def build_transcribe_subgraph(
    config: Optional[TranscribeConfig] = None,
    checkpointer=None,
):
    """构造 transcribe SubGraph。

    Args:
        config: 可调参数，None 表示使用默认 TranscribeConfig()
        checkpointer: 可选 checkpointer，嵌入主 Graph 时传 None

    Returns:
        CompiledGraph: 可直接 invoke / 作为 node 嵌入主 Graph
    """
    config = config or TranscribeConfig()

    builder = StateGraph(TranscribeState)
    builder.add_node("download", make_download_node(config))
    builder.add_node("transcribe", make_transcribe_node(config))
    builder.add_node("summarize", make_summarize_node(config))

    builder.add_edge(START, "download")
    builder.add_edge("download", "transcribe")
    builder.add_edge("transcribe", "summarize")
    builder.add_edge("summarize", END)

    return builder.compile(checkpointer=checkpointer)
