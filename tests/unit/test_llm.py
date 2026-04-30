"""
LLM + SubGraph 集成测试。

改造后 research_subgraph 用 opencli 真实检索，不再调 llm_minimax。
UT-09 更新为验证 _opencli_search 被调用，返回真实格式结果。
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# 确保 ai-pipeline 根目录在 sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestResearchNodeTraceSpan:
    """验证 research_node 正确调用 opencli 检索并返回真实结果。"""

    def _mock_opencli_result(self):
        """模拟 opencli search 返回的标准结果。"""
        return [
            {"rank": 1, "title": "AI Agent 测试视频", "author": "测试作者",
             "score": 1000, "url": "https://www.bilibili.com/video/BVtest001/"},
            {"rank": 2, "title": "AI Agent 进阶", "author": "测试作者2",
             "score": 500, "url": "https://www.bilibili.com/video/BVtest002/"},
        ]

    def test_ut09_research_node_calls_opencli(self):
        """UT-09: research_node 调用 opencli 检索，返回真实视频 URL。"""
        import json
        from subgraphs.research_subgraph.config import ResearchConfig
        from subgraphs.research_subgraph.nodes import make_research_node

        config = ResearchConfig(timeout=30, max_videos=5, min_score=0)
        research_node = make_research_node(config)

        mock_result = self._mock_opencli_result()

        # Mock subprocess.run（opencli 调用）
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = json.dumps(mock_result)

        with patch("subprocess.run", return_value=mock_proc):
            with patch("subgraphs.research_subgraph.nodes._find_opencli",
                       return_value="/mock/opencli"):
                state = {"topic": "AI Agent", "_trace_span": None}
                result = research_node(state)

        assert result["error"] is None
        assert len(result["video_urls"]) == 2
        assert "bilibili.com" in result["video_urls"][0]
        assert result["selected_videos"][0]["title"] == "AI Agent 测试视频"

    def test_research_node_trace_span_none_still_works(self):
        """research_node _trace_span=None 时照常工作（opencli 路径）。"""
        import json
        from subgraphs.research_subgraph.config import ResearchConfig
        from subgraphs.research_subgraph.nodes import make_research_node

        config = ResearchConfig(timeout=30, max_videos=5, min_score=0)
        research_node = make_research_node(config)

        mock_result = self._mock_opencli_result()
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = json.dumps(mock_result)

        with patch("subprocess.run", return_value=mock_proc):
            with patch("subgraphs.research_subgraph.nodes._find_opencli",
                       return_value="/mock/opencli"):
                state = {"topic": "AI Agent"}  # 没有 _trace_span
                result = research_node(state)

        assert result["error"] is None
        assert len(result["video_urls"]) == 2

    def test_research_node_opencli_not_found_returns_error(self):
        """opencli 未安装时返回 error 而不是崩溃。"""
        from subgraphs.research_subgraph.config import ResearchConfig
        from subgraphs.research_subgraph.nodes import make_research_node

        config = ResearchConfig(timeout=30)
        research_node = make_research_node(config)

        with patch("subgraphs.research_subgraph.nodes._find_opencli", return_value=None):
            state = {"topic": "AI Agent"}
            result = research_node(state)

        assert result["error"] is not None
        assert "opencli" in result["error"].lower()
        assert result["video_urls"] == []
