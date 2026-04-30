"""
E2E 测试：Langfuse 未配置时 Pipeline 正常运行。

验证：
  - 不设 LANGFUSE_PUBLIC_KEY
  - 用 mock LLM 跑 research_subgraph
  - 断言：正常返回，无异常
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# 确保 ai-pipeline 根目录在 sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestLangfuseDisabled:
    """Langfuse 未配置时 SubGraph 正常运行。"""

    def test_research_subgraph_without_langfuse(self):
        """不设 LANGFUSE_PUBLIC_KEY，research_subgraph 正常返回。"""
        # 确保 Langfuse 不可用
        env = os.environ.copy()
        env.pop("LANGFUSE_PUBLIC_KEY", None)
        env.pop("LANGFUSE_SECRET_KEY", None)

        with patch.dict(os.environ, env, clear=True):
            # 需要 MINIMAX_CN_API_KEY 存在（mock 掉实际调用）
            os.environ["MINIMAX_CN_API_KEY"] = "fake-key-for-test"

            from subgraphs.research_subgraph.config import ResearchConfig
            from subgraphs.research_subgraph.nodes import make_research_node

            config = ResearchConfig(timeout=60)
            research_node = make_research_node(config)

            with patch("subgraphs.research_subgraph.nodes.llm_minimax") as mock_llm:
                mock_llm.return_value = '[{"title":"测试视频","url":"https://www.bilibili.com/video/BV_test/","platform":"bilibili","note":"测试"}]'

                state = {
                    "topic": "AI Agent 测试",
                    "_trace_span": None,  # Langfuse 未配置
                }

                # 不应抛异常
                result = research_node(state)

                # 验证正常返回
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

            # get_langfuse 返回 None
            assert get_langfuse() is None

            # create_trace 返回 None
            assert create_trace("test", "session-1") is None

            # obs_span(None) 不报错
            with obs_span(None, "test") as s:
                assert s is None

            # flush_trace(None) 不报错
            flush_trace(None)
