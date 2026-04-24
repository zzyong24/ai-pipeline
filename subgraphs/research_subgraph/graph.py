"""research_subgraph 构图函数。

使用：
    from subgraphs.research_subgraph import build_research_subgraph
    subgraph = build_research_subgraph()
    result = subgraph.invoke({"topic": "AI Agent"})
"""
from __future__ import annotations
from typing import Optional

from langgraph.graph import StateGraph, START, END

from .state import ResearchState
from .nodes import make_research_node
from .config import ResearchConfig


def build_research_subgraph(
    config: Optional[ResearchConfig] = None,
    checkpointer=None,
):
    """构造 research SubGraph。

    Args:
        config: 可调参数，None 表示使用默认 ResearchConfig()
        checkpointer: 可选 checkpointer，嵌入主 Graph 时传 None

    Returns:
        CompiledGraph: 可直接 invoke / 作为 node 嵌入主 Graph
    """
    config = config or ResearchConfig()

    builder = StateGraph(ResearchState)
    builder.add_node("research", make_research_node(config))
    builder.add_edge(START, "research")
    builder.add_edge("research", END)

    return builder.compile(checkpointer=checkpointer)
