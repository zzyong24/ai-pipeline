"""routing_subgraph E2E 测试 — happy path（规则命中）。

测试策略：
  - 直接调 routing_subgraph（不启动整个 Pipeline）
  - source_type="video" 命中规则 -> study_doc/reading
  - LLM 不应被调用（mock 用于断言未被调用）
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.resolve()))

from subgraphs.routing_subgraph import build_routing_subgraph, RoutingState
from subgraphs.routing_subgraph.config import RoutingConfig, RoutingRule


class TestRoutingHappyPath:
    """E2E: 规则命中时完整流程测试。"""

    @pytest.fixture
    def subgraph(self):
        """构建带标准规则的 routing_subgraph。"""
        config = RoutingConfig(rules=[
            RoutingRule(source_type="video", content_type="study_doc", topic="reading"),
            RoutingRule(source_type="podcast", content_type="study_doc", topic="reading"),
            RoutingRule(keywords=["论文"], content_type="knowledge_card", topic="ai"),
            RoutingRule(domain="github.com", content_type="note", topic="dev"),
        ])
        return build_routing_subgraph(config)

    def test_video_source_routes_to_study_doc(self, subgraph):
        """source_type=video -> study_doc/reading，LLM 未被调用。"""
        with patch(
            "subgraphs.routing_subgraph.nodes.ChatAnthropic"
        ) as mock_llm_cls:
            input_state: RoutingState = {
                "title": "AI Agent 入门教程",
                "summary": "本视频详细讲解了 AI Agent 的核心概念和实现方法",
                "source_type": "video",
                "source_url": "https://www.bilibili.com/video/BV123456",
            }
            result = subgraph.invoke(input_state)

        # 断言路由结果
        decision = result.get("route_decision")
        assert decision is not None
        assert decision["content_type"] == "study_doc"
        assert decision["topic"] == "reading"
        assert decision["confidence"] == 1.0

        # 断言匹配方法
        assert result.get("match_method") == "rule"

        # 断言 LLM 未被调用
        mock_llm_cls.assert_not_called()

    def test_github_domain_routes_to_note(self, subgraph):
        """domain=github.com -> note/dev，LLM 未被调用。"""
        with patch(
            "subgraphs.routing_subgraph.nodes.ChatAnthropic"
        ) as mock_llm_cls:
            input_state: RoutingState = {
                "title": "LangGraph 源码",
                "summary": "LangGraph 的核心实现",
                "source_type": "web",
                "source_url": "https://github.com/langchain-ai/langgraph",
            }
            result = subgraph.invoke(input_state)

        decision = result.get("route_decision")
        assert decision is not None
        assert decision["content_type"] == "note"
        assert decision["topic"] == "dev"
        mock_llm_cls.assert_not_called()

    def test_keyword_routes_to_knowledge_card(self, subgraph):
        """keywords=[论文] 在标题中命中 -> knowledge_card/ai。"""
        with patch(
            "subgraphs.routing_subgraph.nodes.ChatAnthropic"
        ) as mock_llm_cls:
            input_state: RoutingState = {
                "title": "Attention Is All You Need 论文精读",
                "summary": "对 Transformer 原始论文的逐段解读",
                "source_type": "article",
                "source_url": "https://arxiv.org/abs/1706.03762",
            }
            result = subgraph.invoke(input_state)

        decision = result.get("route_decision")
        assert decision is not None
        assert decision["content_type"] == "knowledge_card"
        assert decision["topic"] == "ai"
        mock_llm_cls.assert_not_called()
