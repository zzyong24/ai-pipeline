"""research_subgraph — 主题研究 SubGraph

输入一个主题，用 LLM 搜索并返回候选视频 URL 列表。

暴露：
    - ResearchState: State 定义
    - build_research_subgraph: 构造函数
"""
from .state import ResearchState
from .graph import build_research_subgraph

__all__ = ["ResearchState", "build_research_subgraph"]
