"""
routing_subgraph Config 定义
=============================

所有可配置项通过 RoutingConfig 注入，SubGraph 内部不读环境变量。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


# 合法的 content_type 枚举值
VALID_CONTENT_TYPES = ["study_doc", "knowledge_card", "article", "note"]


@dataclass
class RoutingRule:
    """单条路由规则。匹配顺序：source_type -> domain -> keywords。

    至少一个匹配条件有值，否则规则无效。
    """
    # 匹配条件（至少一个有值）
    source_type: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    domain: Optional[str] = None

    # 路由结果
    content_type: str = "study_doc"
    topic: str = "reading"
    tags: List[str] = field(default_factory=list)


@dataclass
class RoutingConfig:
    """routing_subgraph 的完整配置。"""
    rules: List[RoutingRule] = field(default_factory=list)
    llm_fallback: bool = True                # 规则不命中时是否用 LLM
    default_content_type: str = "study_doc"  # 兜底 content_type
    default_topic: str = "reading"           # 兜底 topic
    confidence_threshold: float = 0.7        # LLM 置信度阈值（低于此值用默认）
    timeout: int = 30                        # LLM 调用超时（秒）
