"""routing_subgraph 单元测试。覆盖 UT-01 ~ UT-11。

测试策略：
  - 所有 LLM 调用用 mock
  - 直接测试 node 函数（不走完整 SubGraph 编排）
  - 覆盖规则匹配、LLM fallback、校验兜底三个阶段
"""
from __future__ import annotations

import sys
import os
from pathlib import Path

import pytest
from unittest.mock import patch, MagicMock

# 确保 import 路径正确
sys.path.insert(0, str(Path(__file__).parent.parent.parent.resolve()))

from subgraphs.routing_subgraph.config import RoutingConfig, RoutingRule, VALID_CONTENT_TYPES
from subgraphs.routing_subgraph.nodes import (
    make_rule_match_node,
    make_llm_classify_node,
    make_validate_node,
)
from subgraphs.routing_subgraph.state import RoutingState, RouteDecision


# ═════════════════════════════════════════════════════════════════════════════
# 标准规则集
# ═════════════════════════════════════════════════════════════════════════════
DEFAULT_RULES = [
    RoutingRule(source_type="video", content_type="study_doc", topic="reading"),
    RoutingRule(source_type="podcast", content_type="study_doc", topic="reading"),
    RoutingRule(keywords=["论文"], content_type="knowledge_card", topic="ai"),
    RoutingRule(domain="github.com", content_type="note", topic="dev"),
]
DEFAULT_CONFIG = RoutingConfig(rules=DEFAULT_RULES)


# ═════════════════════════════════════════════════════════════════════════════
# UT-01: source_type 规则命中
# ═════════════════════════════════════════════════════════════════════════════
class TestRuleMatch:
    """规则匹配节点测试。"""

    def test_source_type_video_matches(self):
        """UT-01: source_type=video 命中第一条规则。"""
        node = make_rule_match_node(DEFAULT_CONFIG)
        state: RoutingState = {
            "title": "深度学习教程",
            "summary": "视频教程",
            "source_type": "video",
            "source_url": "https://bilibili.com/video/BV123",
        }
        result = node(state)

        assert result["route_decision"]["content_type"] == "study_doc"
        assert result["route_decision"]["topic"] == "reading"
        assert result["route_decision"]["confidence"] == 1.0
        assert result["match_method"] == "rule"

    def test_source_type_podcast_matches(self):
        """UT-02: source_type=podcast 命中 podcast 规则。"""
        node = make_rule_match_node(DEFAULT_CONFIG)
        state: RoutingState = {
            "title": "播客访谈",
            "summary": "一期播客",
            "source_type": "podcast",
            "source_url": "https://podcasts.apple.com/xxx",
        }
        result = node(state)

        assert result["route_decision"]["content_type"] == "study_doc"
        assert result["route_decision"]["topic"] == "reading"
        assert result["match_method"] == "rule"

    def test_domain_matches(self):
        """UT-03: domain=github.com 命中。"""
        node = make_rule_match_node(DEFAULT_CONFIG)
        state: RoutingState = {
            "title": "开源项目",
            "summary": "一个有趣的仓库",
            "source_type": "web",
            "source_url": "https://github.com/user/repo",
        }
        result = node(state)

        assert result["route_decision"]["content_type"] == "note"
        assert result["route_decision"]["topic"] == "dev"

    def test_keyword_matches_in_title(self):
        """UT-04: keywords 命中（关键词在 title 中）。"""
        node = make_rule_match_node(DEFAULT_CONFIG)
        state: RoutingState = {
            "title": "这是一篇论文精读",
            "summary": "内容很好",
            "source_type": "article",
            "source_url": "https://arxiv.org/xxx",
        }
        result = node(state)

        assert result["route_decision"]["content_type"] == "knowledge_card"
        assert result["route_decision"]["topic"] == "ai"

    def test_keyword_matches_in_summary(self):
        """UT-05: keywords 命中（关键词在 summary 中）。"""
        node = make_rule_match_node(DEFAULT_CONFIG)
        state: RoutingState = {
            "title": "学术内容",
            "summary": "本文是一篇关于深度学习的论文解读",
            "source_type": "article",
            "source_url": "https://example.com",
        }
        result = node(state)

        assert result["route_decision"]["content_type"] == "knowledge_card"
        assert result["route_decision"]["topic"] == "ai"

    def test_no_rule_matches(self):
        """UT-06: 无规则命中时返回空 dict。"""
        node = make_rule_match_node(DEFAULT_CONFIG)
        state: RoutingState = {
            "title": "生活随记",
            "summary": "今天天气不错",
            "source_type": "web",
            "source_url": "https://example.com/life",
        }
        result = node(state)

        assert result == {}

    def test_first_rule_wins(self):
        """UT-07: 多条规则可能匹配时，首条优先。"""
        # video 规则在 keywords 规则之前
        node = make_rule_match_node(DEFAULT_CONFIG)
        state: RoutingState = {
            "title": "论文视频解读",
            "summary": "这是一个论文的视频讲解",
            "source_type": "video",
            "source_url": "https://bilibili.com/video/BV456",
        }
        result = node(state)

        # source_type=video 应先命中
        assert result["route_decision"]["content_type"] == "study_doc"
        assert result["route_decision"]["topic"] == "reading"


# ═════════════════════════════════════════════════════════════════════════════
# UT-08 ~ UT-09: LLM 分类节点测试
# ═════════════════════════════════════════════════════════════════════════════
class TestLLMClassify:
    """LLM 分类节点测试。"""

    def test_skip_when_rule_already_matched(self):
        """UT-08: 规则已命中时跳过 LLM。"""
        node = make_llm_classify_node(DEFAULT_CONFIG)
        state: RoutingState = {
            "title": "test",
            "summary": "test",
            "source_type": "video",
            "source_url": "",
            "route_decision": {
                "content_type": "study_doc",
                "topic": "reading",
                "tags": [],
                "confidence": 1.0,
            },
        }
        result = node(state)
        assert result == {}

    def test_llm_fallback_disabled(self):
        """UT-09: llm_fallback=False 时使用默认值。"""
        config = RoutingConfig(rules=[], llm_fallback=False)
        node = make_llm_classify_node(config)
        state: RoutingState = {
            "title": "test",
            "summary": "test",
            "source_type": "web",
            "source_url": "",
        }
        result = node(state)

        assert result["route_decision"]["content_type"] == "study_doc"
        assert result["route_decision"]["topic"] == "reading"
        assert result["route_decision"]["confidence"] == 0.0

    def test_llm_call_success(self):
        """UT-10: LLM 调用成功，返回合法结果。"""
        config = RoutingConfig(rules=[], llm_fallback=True)
        node = make_llm_classify_node(config)

        mock_result = MagicMock()
        mock_result.content_type = "article"
        mock_result.topic = "ai"
        mock_result.tags = ["观点"]
        mock_result.confidence = 0.9
        mock_result.reason = "分析类文章"

        mock_structured = MagicMock()
        mock_structured.invoke.return_value = mock_result

        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_structured

        with patch(
            "subgraphs.routing_subgraph.nodes.ChatAnthropic",
            return_value=mock_llm,
        ):
            state: RoutingState = {
                "title": "AI 行业观察",
                "summary": "对 AI 行业的深度分析",
                "source_type": "article",
                "source_url": "https://example.com",
            }
            result = node(state)

        assert result["route_decision"]["content_type"] == "article"
        assert result["route_decision"]["topic"] == "ai"
        assert result["match_method"] == "llm"

    def test_llm_call_failure_fallback(self):
        """UT-11: LLM 调用失败，fallback 到默认值不崩溃。"""
        config = RoutingConfig(
            rules=[],
            llm_fallback=True,
            default_content_type="study_doc",
            default_topic="reading",
        )
        node = make_llm_classify_node(config)

        with patch(
            "subgraphs.routing_subgraph.nodes.ChatAnthropic",
            side_effect=Exception("API timeout"),
        ):
            state: RoutingState = {
                "title": "无法分类",
                "summary": "随机内容",
                "source_type": "web",
                "source_url": "",
            }
            result = node(state)

        assert result["route_decision"]["content_type"] == "study_doc"
        assert result["route_decision"]["topic"] == "reading"
        assert "error" in result


# ═════════════════════════════════════════════════════════════════════════════
# Validate 节点测试
# ═════════════════════════════════════════════════════════════════════════════
class TestValidate:
    """校验节点测试。"""

    def test_valid_decision_passes_through(self):
        """合法决策直接透传。"""
        node = make_validate_node(DEFAULT_CONFIG)
        state: RoutingState = {
            "route_decision": {
                "content_type": "article",
                "topic": "ai",
                "tags": ["test"],
                "confidence": 0.9,
            },
            "match_method": "llm",
        }
        result = node(state)

        assert result["route_decision"]["content_type"] == "article"

    def test_none_decision_fallback(self):
        """route_decision=None 时 fallback。"""
        node = make_validate_node(DEFAULT_CONFIG)
        state: RoutingState = {}
        result = node(state)

        assert result["route_decision"]["content_type"] == "study_doc"
        assert result["route_decision"]["topic"] == "reading"
        assert "error" in result

    def test_invalid_content_type_fallback(self):
        """content_type 不合法时 fallback。"""
        node = make_validate_node(DEFAULT_CONFIG)
        state: RoutingState = {
            "route_decision": {
                "content_type": "invalid_type",
                "topic": "ai",
                "tags": [],
                "confidence": 0.8,
            },
            "match_method": "llm",
        }
        result = node(state)

        assert result["route_decision"]["content_type"] == "study_doc"
        assert "error" in result
