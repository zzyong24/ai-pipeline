"""routing_subgraph E2E 测试 — LLM fallback 路径。

测试策略：
  - 空规则列表，强制走 LLM
  - mock ChatAnthropic 返回合法 RouteDecision
  - 断言 match_method=="llm"
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.resolve()))

from subgraphs.routing_subgraph import build_routing_subgraph, RoutingState
from subgraphs.routing_subgraph.config import RoutingConfig


class TestRoutingLLMFallback:
    """E2E: 规则不命中 -> LLM fallback 路径。"""

    def _make_mock_llm(self, content_type="article", topic="ai",
                       tags=None, confidence=0.85):
        """创建 mock LLM 实例。"""
        mock_result = MagicMock()
        mock_result.content_type = content_type
        mock_result.topic = topic
        mock_result.tags = tags or ["test"]
        mock_result.confidence = confidence
        mock_result.reason = "mock reason"

        mock_structured = MagicMock()
        mock_structured.invoke.return_value = mock_result

        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_structured

        return mock_llm

    def test_empty_rules_triggers_llm(self):
        """空规则列表 -> LLM fallback，match_method=llm。"""
        config = RoutingConfig(rules=[], llm_fallback=True)
        mock_llm = self._make_mock_llm(
            content_type="knowledge_card",
            topic="ai",
            tags=["论文", "深度学习"],
            confidence=0.9,
        )

        with patch(
            "subgraphs.routing_subgraph.nodes.ChatAnthropic",
            return_value=mock_llm,
        ):
            subgraph = build_routing_subgraph(config)
            input_state: RoutingState = {
                "title": "Scaling Laws 研究综述",
                "summary": "对大模型 Scaling Laws 的系统性总结和分析",
                "source_type": "article",
                "source_url": "https://arxiv.org/abs/xxx",
            }
            result = subgraph.invoke(input_state)

        decision = result.get("route_decision")
        assert decision is not None
        assert decision["content_type"] == "knowledge_card"
        assert decision["topic"] == "ai"
        assert result.get("match_method") == "llm"

    def test_llm_low_confidence_uses_default(self):
        """LLM 置信度低于阈值时使用默认值。"""
        config = RoutingConfig(
            rules=[],
            llm_fallback=True,
            confidence_threshold=0.7,
            default_content_type="study_doc",
            default_topic="reading",
        )
        mock_llm = self._make_mock_llm(
            content_type="article",
            topic="ai",
            confidence=0.3,  # 低于阈值
        )

        with patch(
            "subgraphs.routing_subgraph.nodes.ChatAnthropic",
            return_value=mock_llm,
        ):
            subgraph = build_routing_subgraph(config)
            input_state: RoutingState = {
                "title": "模糊内容",
                "summary": "无法确定分类",
                "source_type": "web",
                "source_url": "https://example.com",
            }
            result = subgraph.invoke(input_state)

        decision = result.get("route_decision")
        assert decision is not None
        # 低置信度应 fallback 到默认值
        assert decision["content_type"] == "study_doc"
        assert decision["topic"] == "reading"

    def test_llm_exception_does_not_crash(self):
        """LLM 抛异常时 SubGraph 不崩溃，fallback 到默认值。"""
        config = RoutingConfig(
            rules=[],
            llm_fallback=True,
            default_content_type="study_doc",
            default_topic="reading",
        )

        with patch(
            "subgraphs.routing_subgraph.nodes.ChatAnthropic",
            side_effect=Exception("Network error"),
        ):
            subgraph = build_routing_subgraph(config)
            input_state: RoutingState = {
                "title": "随机内容",
                "summary": "不重要",
                "source_type": "web",
                "source_url": "https://example.com",
            }
            result = subgraph.invoke(input_state)

        decision = result.get("route_decision")
        assert decision is not None
        assert decision["content_type"] == "study_doc"
        assert decision["topic"] == "reading"
        # 应该有 error 记录
        assert result.get("error") is not None

    def test_llm_fallback_disabled_uses_default(self):
        """llm_fallback=False 时不调 LLM，直接使用默认值。"""
        config = RoutingConfig(
            rules=[],
            llm_fallback=False,
            default_content_type="note",
            default_topic="dev",
        )

        with patch(
            "subgraphs.routing_subgraph.nodes.ChatAnthropic"
        ) as mock_cls:
            subgraph = build_routing_subgraph(config)
            input_state: RoutingState = {
                "title": "随便什么",
                "summary": "无所谓",
                "source_type": "web",
                "source_url": "https://example.com",
            }
            result = subgraph.invoke(input_state)

        decision = result.get("route_decision")
        assert decision is not None
        assert decision["content_type"] == "note"
        assert decision["topic"] == "dev"
        # LLM 不应被实例化
        mock_cls.assert_not_called()
