"""
routing_subgraph 独立测试
==========================

用法：
    python -m subgraphs.routing_subgraph.test

覆盖三种情况：
  1. 规则命中（video -> study_doc/reading，不调 LLM）
  2. LLM fallback（空规则列表，mock LLM）
  3. LLM 也失败时，fallback 不崩溃
"""
from __future__ import annotations

import sys
import os
from unittest.mock import patch, MagicMock
from pathlib import Path

# 确保 import 路径正确
sys.path.insert(0, str(Path(__file__).parent.parent.parent.resolve()))

from subgraphs.routing_subgraph import build_routing_subgraph, RoutingState
from subgraphs.routing_subgraph.config import RoutingConfig, RoutingRule


def test_rule_match():
    """测试 1: 规则命中 — video -> study_doc/reading"""
    print("\n" + "=" * 60)
    print("测试 1: 规则命中（source_type=video）")
    print("=" * 60)

    config = RoutingConfig(rules=[
        RoutingRule(source_type="video", content_type="study_doc", topic="reading"),
        RoutingRule(keywords=["论文"], content_type="knowledge_card", topic="ai"),
    ])
    subgraph = build_routing_subgraph(config)

    input_state: RoutingState = {
        "title": "深度学习入门教程",
        "summary": "本视频介绍了深度学习的基本概念",
        "source_type": "video",
        "source_url": "https://www.bilibili.com/video/BV123",
    }

    result = subgraph.invoke(input_state)

    decision = result.get("route_decision")
    assert decision is not None, "route_decision 不应为 None"
    assert decision["content_type"] == "study_doc", f"期望 study_doc，实际 {decision['content_type']}"
    assert decision["topic"] == "reading", f"期望 reading，实际 {decision['topic']}"
    assert decision["confidence"] == 1.0, f"规则命中应为 1.0，实际 {decision['confidence']}"
    assert result.get("match_method") == "rule", f"期望 rule，实际 {result.get('match_method')}"

    print(f"  -> 通过! decision={decision}")


def test_llm_fallback():
    """测试 2: 空规则列表，走 LLM fallback（mock）"""
    print("\n" + "=" * 60)
    print("测试 2: LLM fallback（mock ChatAnthropic）")
    print("=" * 60)

    config = RoutingConfig(rules=[], llm_fallback=True)

    # Mock LLM 返回
    mock_result = MagicMock()
    mock_result.content_type = "knowledge_card"
    mock_result.topic = "ai"
    mock_result.tags = ["论文", "研究"]
    mock_result.confidence = 0.85
    mock_result.reason = "标题包含研究相关内容"

    mock_structured = MagicMock()
    mock_structured.invoke.return_value = mock_result

    mock_llm_instance = MagicMock()
    mock_llm_instance.with_structured_output.return_value = mock_structured

    with patch("subgraphs.routing_subgraph.nodes.ChatAnthropic", return_value=mock_llm_instance):
        subgraph = build_routing_subgraph(config)
        input_state: RoutingState = {
            "title": "Transformer 论文精读",
            "summary": "本文深度解读了 Attention Is All You Need 论文",
            "source_type": "article",
            "source_url": "https://arxiv.org/abs/1706.03762",
        }
        result = subgraph.invoke(input_state)

    decision = result.get("route_decision")
    assert decision is not None, "route_decision 不应为 None"
    assert decision["content_type"] == "knowledge_card"
    assert decision["topic"] == "ai"
    assert result.get("match_method") == "llm"

    print(f"  -> 通过! decision={decision}")


def test_llm_failure_fallback():
    """测试 3: LLM 调用失败，fallback 到默认值不崩溃"""
    print("\n" + "=" * 60)
    print("测试 3: LLM 调用失败 fallback")
    print("=" * 60)

    config = RoutingConfig(
        rules=[],
        llm_fallback=True,
        default_content_type="study_doc",
        default_topic="reading",
    )

    # Mock LLM 抛异常
    mock_llm_instance = MagicMock()
    mock_llm_instance.with_structured_output.side_effect = Exception("API 连接失败")

    with patch("subgraphs.routing_subgraph.nodes.ChatAnthropic", return_value=mock_llm_instance):
        subgraph = build_routing_subgraph(config)
        input_state: RoutingState = {
            "title": "某内容",
            "summary": "无法分类的内容",
            "source_type": "web",
            "source_url": "https://example.com",
        }
        result = subgraph.invoke(input_state)

    decision = result.get("route_decision")
    assert decision is not None, "route_decision 不应为 None（即使 LLM 失败）"
    assert decision["content_type"] == "study_doc", "LLM 失败应 fallback 到默认值"
    assert decision["topic"] == "reading"

    print(f"  -> 通过! decision={decision}")
    print(f"  -> error={result.get('error')}")


if __name__ == "__main__":
    test_rule_match()
    test_llm_fallback()
    test_llm_failure_fallback()
    print("\n" + "=" * 60)
    print("全部测试通过!")
    print("=" * 60)
