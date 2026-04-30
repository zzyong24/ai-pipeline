"""
E2E 测试：Langfuse 未配置时 Pipeline 正常运行。

验证：
  - 不设 LANGFUSE_PUBLIC_KEY
  - 用 mock opencli 跑 research_subgraph（改造后不再调 llm_minimax）
  - 断言：正常返回，无异常
"""
import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# 确保 ai-pipeline 根目录在 sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestLangfuseDisabled:
    """Langfuse 未配置时 SubGraph 正常运行。"""

    def test_research_subgraph_without_langfuse(self):
        """不设 LANGFUSE_PUBLIC_KEY，research_subgraph 用 opencli mock 正常返回。"""
        env = os.environ.copy()
        env.pop("LANGFUSE_PUBLIC_KEY", None)
        env.pop("LANGFUSE_SECRET_KEY", None)

        mock_opencli_output = json.dumps([
            {"rank": 1, "title": "AI Agent 测试视频", "author": "测试作者",
             "score": 1000, "url": "https://www.bilibili.com/video/BV_test/"},
        ])
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = mock_opencli_output

        with patch.dict(os.environ, env, clear=True):
            from subgraphs.research_subgraph.config import ResearchConfig
            from subgraphs.research_subgraph.nodes import make_research_node

            config = ResearchConfig(timeout=30, min_score=0)
            research_node = make_research_node(config)

            with patch("subprocess.run", return_value=mock_proc):
                with patch("subgraphs.research_subgraph.nodes._find_opencli",
                           return_value="/mock/opencli"):
                    state = {
                        "topic": "AI Agent 测试",
                        "_trace_span": None,
                    }
                    result = research_node(state)

        assert result["error"] is None
        assert len(result["video_urls"]) == 1
        assert "bilibili.com" in result["video_urls"][0]

    def test_observability_module_graceful_when_disabled(self):
        """obs_span / create_trace / flush_trace 在未配置时静默跳过。"""
        env = os.environ.copy()
        env.pop("LANGFUSE_PUBLIC_KEY", None)

        with patch.dict(os.environ, env, clear=True):
            from subgraphs.shared.observability import (
                get_langfuse, create_trace, obs_span, flush_trace
            )

            assert get_langfuse() is None
            assert create_trace("test", "session-1") is None

            with obs_span(None, "test") as s:
                assert s is None

            flush_trace(None)
