"""write_book_subgraph 构图函数。

使用：
    from subgraphs.write_book_subgraph import build_write_book_subgraph
    subgraph = build_write_book_subgraph(config)
    result = subgraph.invoke({"topic": "xxx", "summaries": [...]})
"""
from __future__ import annotations
from typing import Optional

from langgraph.graph import StateGraph, START, END

from .state import WriteBookState
from .nodes import make_aggregate_node, make_write_node
from .config import WriteBookConfig


def build_write_book_subgraph(
    config: Optional[WriteBookConfig] = None,
    checkpointer=None,
):
    """构造 write_book SubGraph。

    Args:
        config: 可调参数
        checkpointer: 可选 checkpointer

    Returns:
        CompiledGraph
    """
    config = config or WriteBookConfig()

    builder = StateGraph(WriteBookState)
    builder.add_node("aggregate", make_aggregate_node(config))
    builder.add_node("write", make_write_node(config))

    builder.add_edge(START, "aggregate")
    builder.add_edge("aggregate", "write")
    builder.add_edge("write", END)

    return builder.compile(checkpointer=checkpointer)
