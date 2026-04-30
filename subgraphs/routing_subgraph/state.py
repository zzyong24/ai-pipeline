"""
routing_subgraph State 定义
============================

独立 State Schema，不依赖任何 Pipeline 的主 State。
"""
from __future__ import annotations

from typing import TypedDict, List, Optional, Any


class RouteDecision(TypedDict):
    """路由决策结果。"""
    content_type: str    # "study_doc" | "knowledge_card" | "article" | "note"
    topic: str           # "reading" | "ai" | "dev" | ...
    tags: List[str]      # 分类标签
    confidence: float    # 规则命中=1.0，LLM 输出置信度


class RoutingState(TypedDict, total=False):
    """routing_subgraph 的独立 State。"""

    # ───────────── 输入 ─────────────
    title: str                   # 内容标题
    summary: str                 # 内容摘要（前 500 字）
    source_type: str             # "video" | "podcast" | "article" | "web"
    source_url: str              # 来源 URL
    raw_content: str             # 原始内容（可选，用于更精准分类）

    # ───────────── 透传（主 Graph 注入，SubGraph 不创建） ─────────────
    _trace_span: Optional[Any]   # Langfuse trace span（预留接口）

    # ───────────── 中间状态 ─────────────
    match_method: str            # "rule" | "llm"
    matched_rule: Optional[str]  # 命中的规则描述

    # ───────────── 输出 ─────────────
    route_decision: Optional[RouteDecision]  # 最终路由决策
    error: Optional[str]                     # 错误信息
