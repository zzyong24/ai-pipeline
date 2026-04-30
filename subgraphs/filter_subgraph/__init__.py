from .nodes import make_filter_node
from .state import FilterState
from .config import FilterConfig
from langgraph.graph import StateGraph, START, END

def build_filter_subgraph(config: FilterConfig = None):
    config = config or FilterConfig()
    builder = StateGraph(FilterState)
    builder.add_node("filter", make_filter_node(config))
    builder.add_edge(START, "filter")
    builder.add_edge("filter", END)
    return builder.compile()

__all__ = ["build_filter_subgraph", "FilterState", "FilterConfig"]
