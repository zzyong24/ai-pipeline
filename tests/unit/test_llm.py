"""
LLM + SubGraph 集成测试。

覆盖：
  UT-09: research_node _trace_span=mock_trace 时 llm_minimax 收到 trace_span
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# 确保 ai-pipeline 根目录在 sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestResearchNodeTraceSpan:
    """验证 research_node 正确透传 _trace_span 给 llm_minimax。"""

    def test_ut09_research_node_passes_trace_span(self):
        """UT-09: research_node 从 state 取 _trace_span 并传给 llm_minimax。"""
        from subgraphs.research_subgraph.config import ResearchConfig
        from subgraphs.research_subgraph.nodes import make_research_node

        config = ResearchConfig(timeout=60)
        research_node = make_research_node(config)

        mock_trace = MagicMock()

        # Mock llm_minimax 并验证参数
        with patch("subgraphs.research_subgraph.nodes.llm_minimax") as mock_llm:
            mock_llm.return_value = '[{"title":"测试","url":"https://www.bilibili.com/video/BVtest/","platform":"bilibili","note":"测试"}]'

            state = {
                "topic": "AI Agent",
                "_trace_span": mock_trace,
            }

            result = research_node(state)

            # 验证 llm_minimax 被调用，且 trace_span 参数正确
            mock_llm.assert_called_once()
            call_kwargs = mock_llm.call_args[1]
            assert call_kwargs["trace_span"] is mock_trace
            assert call_kwargs["generation_name"] == "research/search"

            # 验证正常返回
            assert result["error"] is None
            assert len(result["video_urls"]) == 1

    def test_research_node_trace_span_none_still_works(self):
        """research_node _trace_span=None 时照常工作。"""
        from subgraphs.research_subgraph.config import ResearchConfig
        from subgraphs.research_subgraph.nodes import make_research_node

        config = ResearchConfig(timeout=60)
        research_node = make_research_node(config)

        with patch("subgraphs.research_subgraph.nodes.llm_minimax") as mock_llm:
            mock_llm.return_value = '[{"title":"测试","url":"https://www.bilibili.com/video/BVtest/","platform":"bilibili","note":"测试"}]'

            state = {
                "topic": "AI Agent",
                # 没有 _trace_span 或为 None
            }

            result = research_node(state)

            # 验证 trace_span=None 被传入
            call_kwargs = mock_llm.call_args[1]
            assert call_kwargs["trace_span"] is None

            # 正常返回
            assert result["error"] is None
