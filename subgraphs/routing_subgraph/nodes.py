"""
routing_subgraph 节点实现
==========================

三个 node 工厂函数：
  - make_rule_match_node: 规则匹配（优先级最高）
  - make_llm_classify_node: LLM 分类（fallback）
  - make_validate_node: 校验兜底（最后一道防线）
"""
from __future__ import annotations

from typing import Dict, Any, List

from langchain_anthropic import ChatAnthropic

from .state import RoutingState, RouteDecision
from .config import RoutingConfig, RoutingRule, VALID_CONTENT_TYPES


def make_rule_match_node(config: RoutingConfig):
    """工厂函数：创建规则匹配节点。

    匹配逻辑：遍历 config.rules，按 source_type -> domain -> keywords 顺序。
    首个命中即返回，不继续匹配。
    """

    def rule_match_node(state: RoutingState) -> Dict[str, Any]:
        """规则匹配节点：遍历规则集，首个命中即输出 RouteDecision。"""
        title = state.get("title", "")
        summary = state.get("summary", "")
        source_type = state.get("source_type", "")
        source_url = state.get("source_url", "")

        for rule in config.rules:
            if _rule_matches(rule, source_type, source_url, title, summary):
                decision: RouteDecision = {
                    "content_type": rule.content_type,
                    "topic": rule.topic,
                    "tags": rule.tags[:],
                    "confidence": 1.0,
                }
                print(
                    f"[routing_subgraph:rule_match] "
                    f"命中规则: {_rule_desc(rule)} -> "
                    f"{decision['content_type']}/{decision['topic']}"
                )
                return {
                    "route_decision": decision,
                    "match_method": "rule",
                    "matched_rule": _rule_desc(rule),
                }

        print("[routing_subgraph:rule_match] 无规则命中，交给 LLM")
        return {}

    return rule_match_node


def _rule_matches(
    rule: RoutingRule,
    source_type: str,
    source_url: str,
    title: str,
    summary: str,
) -> bool:
    """判断单条规则是否命中。按 source_type -> domain -> keywords 顺序。"""
    # source_type 匹配
    if rule.source_type and source_type == rule.source_type:
        return True

    # domain 匹配
    if rule.domain and rule.domain in source_url:
        return True

    # keywords 匹配（任一关键词出现在 title 或 summary 中）
    if rule.keywords:
        text = f"{title} {summary}"
        for kw in rule.keywords:
            if kw in text:
                return True

    return False


def _rule_desc(rule: RoutingRule) -> str:
    """生成规则的可读描述。"""
    parts = []
    if rule.source_type:
        parts.append(f"source_type={rule.source_type}")
    if rule.domain:
        parts.append(f"domain={rule.domain}")
    if rule.keywords:
        parts.append(f"keywords={rule.keywords}")
    return f"RoutingRule({', '.join(parts)} -> {rule.content_type}/{rule.topic})"


def make_llm_classify_node(config: RoutingConfig):
    """工厂函数：创建 LLM 分类节点。

    仅在规则未命中且 llm_fallback=True 时调用 LLM。
    失败时 fallback 到默认值，不抛异常。
    """

    def llm_classify_node(state: RoutingState) -> Dict[str, Any]:
        """LLM 分类节点：规则未命中时用 LLM 做内容分类。"""
        # 规则已命中，跳过 LLM
        if state.get("route_decision"):
            print("[routing_subgraph:llm_classify] 规则已命中，跳过 LLM")
            return {}

        # 不启用 LLM fallback，返回默认值
        if not config.llm_fallback:
            print("[routing_subgraph:llm_classify] LLM fallback 未启用，使用默认值")
            return {
                "route_decision": _make_default_decision(config),
                "match_method": "rule",
            }

        # 调用 LLM
        try:
            decision = _call_llm_classify(state, config)
            print(
                f"[routing_subgraph:llm_classify] LLM 返回: "
                f"{decision['content_type']}/{decision['topic']} "
                f"(confidence={decision['confidence']})"
            )

            # 置信度过低，使用默认值
            if decision["confidence"] < config.confidence_threshold:
                print(
                    f"[routing_subgraph:llm_classify] "
                    f"置信度 {decision['confidence']} < {config.confidence_threshold}，使用默认值"
                )
                return {
                    "route_decision": _make_default_decision(config),
                    "match_method": "llm",
                }

            return {
                "route_decision": decision,
                "match_method": "llm",
            }
        except Exception as e:
            print(f"[routing_subgraph:llm_classify] LLM 调用失败: {e}")
            return {
                "route_decision": _make_default_decision(config),
                "match_method": "llm",
                "error": f"LLM classify failed: {e}",
            }

    return llm_classify_node


def _call_llm_classify(state: RoutingState, config: RoutingConfig) -> RouteDecision:
    """实际调用 LLM 做分类。使用 langchain_anthropic 对接 MiniMax。"""
    import os
    from pydantic import BaseModel

    class RouteDecisionSchema(BaseModel):
        content_type: str
        topic: str
        tags: list[str]
        confidence: float
        reason: str

    llm = ChatAnthropic(
        model="MiniMax-M2.7",
        api_key=os.environ.get("MINIMAX_API_KEY", ""),
        base_url="https://api.minimaxi.com/anthropic",
        max_tokens=512,
        timeout=config.timeout,
    )
    structured_llm = llm.with_structured_output(RouteDecisionSchema)

    prompt = _build_classify_prompt(state)
    result = structured_llm.invoke(prompt)

    return {
        "content_type": result.content_type,
        "topic": result.topic,
        "tags": result.tags,
        "confidence": result.confidence,
    }


def _build_classify_prompt(state: RoutingState) -> str:
    """构建 LLM 分类的 prompt。"""
    title = state.get("title", "")
    summary = state.get("summary", "")
    source_type = state.get("source_type", "")

    return f"""你是一个内容分类器。根据以下信息，判断这段内容应该归类为什么类型。

## 输入信息
- 标题：{title}
- 摘要：{summary[:300]}
- 来源类型：{source_type}

## 合法的 content_type 值
- study_doc: 学习文档（视频笔记、播客笔记、教程等）
- knowledge_card: 知识卡片（论文、研究、实验报告等）
- article: 文章（观点、评论、分析等）
- note: 笔记（代码片段、备忘、灵感等）

## 合法的 topic 值
- reading: 阅读/学习
- ai: 人工智能
- dev: 开发/编程
- life: 生活
- business: 商业

## 输出要求
返回 JSON，包含 content_type, topic, tags (list[str]), confidence (0-1), reason (简短理由)。
"""


def make_validate_node(config: RoutingConfig):
    """工厂函数：创建校验节点。

    最后一道防线：确保任何情况下都输出合法的 RouteDecision。
    """

    def validate_node(state: RoutingState) -> Dict[str, Any]:
        """校验节点：确保 route_decision 合法，不合法则 fallback。"""
        decision = state.get("route_decision")
        method = state.get("match_method", "unknown")
        error = state.get("error")

        # 无决策 → fallback
        if decision is None:
            print("[routing_subgraph:validate] 无 route_decision，使用默认值")
            return {
                "route_decision": _make_default_decision(config),
                "error": error or "No route decision produced",
            }

        # content_type 不合法 → fallback
        if decision.get("content_type") not in VALID_CONTENT_TYPES:
            print(
                f"[routing_subgraph:validate] "
                f"content_type '{decision.get('content_type')}' 不合法，使用默认值"
            )
            return {
                "route_decision": _make_default_decision(config),
                "error": f"Invalid content_type: {decision.get('content_type')}",
            }

        # 合法 → 透传
        print(
            f"[routing_subgraph:validate] -> "
            f"{decision['content_type']}/{decision['topic']} "
            f"(method={method})"
        )
        return {"route_decision": decision}

    return validate_node


def _make_default_decision(config: RoutingConfig) -> RouteDecision:
    """生成默认的 RouteDecision（兜底）。"""
    return {
        "content_type": config.default_content_type,
        "topic": config.default_topic,
        "tags": [],
        "confidence": 0.0,
    }
