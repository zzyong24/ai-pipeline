from .nodes import make_extract_node
from .state import TextExtractState
from .config import TextExtractConfig
from langgraph.graph import StateGraph, START, END

def build_text_extract_subgraph(config: TextExtractConfig = None):
    config = config or TextExtractConfig()
    builder = StateGraph(TextExtractState)
    builder.add_node("extract", make_extract_node(config))
    builder.add_edge(START, "extract")
    builder.add_edge("extract", END)
    return builder.compile()

__all__ = ["build_text_extract_subgraph", "TextExtractState", "TextExtractConfig"]
