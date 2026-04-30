"""
routing_subgraph — 内容路由 SubGraph
====================================

根据输入内容的标题、摘要、来源类型，决定内容分类（content_type + topic + tags）。
优先用规则匹配，fallback 到 LLM 分类。
"""
from .graph import build_routing_subgraph
from .state import RoutingState, RouteDecision
from .config import RoutingConfig, RoutingRule

__all__ = [
    "build_routing_subgraph",
    "RoutingState",
    "RouteDecision",
    "RoutingConfig",
    "RoutingRule",
]
