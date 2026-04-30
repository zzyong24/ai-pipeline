"""
routing_subgraph 图编排
========================

图结构：rule_match -> llm_classify -> validate -> END

三步线性流水线，不需要 conditional edge：
  1. rule_match: 尝试规则匹配
  2. llm_classify: 规则未命中时调 LLM（内部判断是否跳过）
  3. validate: 最终校验兜底
"""
from __future__ import annotations

from langgraph.graph import StateGraph, END

from .state import RoutingState
from .config import RoutingConfig
from .nodes import make_rule_match_node, make_llm_classify_node, make_validate_node


def build_routing_subgraph(config: RoutingConfig):
    """构建 routing_subgraph。

    Args:
        config: 路由配置（规则列表、LLM fallback 开关、默认值等）

    Returns:
        已编译的 CompiledStateGraph
    """
    builder = StateGraph(RoutingState)

    builder.add_node("rule_match", make_rule_match_node(config))
    builder.add_node("llm_classify", make_llm_classify_node(config))
    builder.add_node("validate", make_validate_node(config))

    builder.set_entry_point("rule_match")
    builder.add_edge("rule_match", "llm_classify")
    builder.add_edge("llm_classify", "validate")
    builder.add_edge("validate", END)

    return builder.compile()
