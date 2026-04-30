"""
Langfuse 可观测单元测试。

覆盖：
  UT-01: get_langfuse() 未配置返回 None
  UT-02: get_langfuse() 已配置返回实例
  UT-03: langfuse 包未安装时返回 None
  UT-04: llm_minimax trace_span=None 时不调 span 方法
  UT-05: llm_minimax trace_span=mock_span 时调用 generation
  UT-06: llm_minimax API 失败时 gen.end(level="ERROR") 被调
  UT-07: obs_span 上下文正常时 s.end() 被调
  UT-08: obs_span 上下文异常时 s.end(level="ERROR") 被调，异常继续传播
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# 确保 ai-pipeline 根目录在 sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestGetLangfuse:
    """UT-01 ~ UT-03: get_langfuse() 行为测试。"""

    def test_ut01_no_public_key_returns_none(self):
        """UT-01: LANGFUSE_PUBLIC_KEY 未设置时返回 None。"""
        env = os.environ.copy()
        env.pop("LANGFUSE_PUBLIC_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            from subgraphs.shared.observability import get_langfuse
            result = get_langfuse()
            assert result is None

    def test_ut02_with_public_key_returns_instance(self):
        """UT-02: LANGFUSE_PUBLIC_KEY 已设置时返回 Langfuse 实例。"""
        mock_langfuse_instance = MagicMock()
        mock_langfuse_module = MagicMock()
        mock_langfuse_module.Langfuse = MagicMock(return_value=mock_langfuse_instance)

        with patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "pk-lf-test"}):
            with patch.dict("sys.modules", {"langfuse": mock_langfuse_module}):
                from subgraphs.shared import observability
                import importlib
                importlib.reload(observability)
                result = observability.get_langfuse()
                assert result is mock_langfuse_instance

    def test_ut03_import_error_returns_none(self):
        """UT-03: langfuse 包未安装（ImportError）时返回 None。"""
        # Remove langfuse from sys.modules if present
        modules_to_remove = [k for k in sys.modules if k == "langfuse" or k.startswith("langfuse.")]
        saved = {}
        for k in modules_to_remove:
            saved[k] = sys.modules.pop(k)

        original_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

        def fake_import(name, *args, **kwargs):
            if name == "langfuse" or name.startswith("langfuse."):
                raise ImportError(f"No module named '{name}'")
            return original_import(name, *args, **kwargs)

        with patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "pk-lf-test"}):
            with patch("builtins.__import__", side_effect=fake_import):
                from subgraphs.shared import observability
                import importlib
                importlib.reload(observability)
                result = observability.get_langfuse()
                assert result is None

        # Restore
        sys.modules.update(saved)


class TestLlmMinimaxObservability:
    """UT-04 ~ UT-06: llm_minimax 中的 Langfuse 埋点。"""

    def _mock_successful_response(self):
        """构造成功的 MiniMax 响应 mock。"""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "测试回复"}}],
            "usage": {"total_tokens": 42},
        }
        return mock_resp

    def test_ut04_trace_span_none_no_generation_call(self):
        """UT-04: trace_span=None 时不调用任何 span/generation 方法。"""
        mock_resp = self._mock_successful_response()

        with patch.dict(os.environ, {"MINIMAX_CN_API_KEY": "test-key"}):
            with patch("requests.post", return_value=mock_resp):
                from subgraphs.shared.llm import llm_minimax
                result = llm_minimax("你好", trace_span=None)
                assert result == "测试回复"

    def test_ut05_trace_span_mock_calls_generation(self):
        """UT-05: trace_span=mock_span 时调用 generation。"""
        mock_resp = self._mock_successful_response()
        mock_span = MagicMock()
        mock_gen = MagicMock()
        mock_span.generation.return_value = mock_gen

        with patch.dict(os.environ, {"MINIMAX_CN_API_KEY": "test-key"}):
            with patch("requests.post", return_value=mock_resp):
                from subgraphs.shared.llm import llm_minimax
                result = llm_minimax("你好", trace_span=mock_span, generation_name="test/gen")

                # 验证 generation 被创建
                mock_span.generation.assert_called_once()
                call_kwargs = mock_span.generation.call_args[1]
                assert call_kwargs["name"] == "test/gen"
                assert call_kwargs["model"] == "MiniMax-M2"
                assert "你好" in call_kwargs["input"]

                # 验证 gen.end 被调用（成功）
                mock_gen.end.assert_called_once()
                end_kwargs = mock_gen.end.call_args[1]
                assert "测试回复" in end_kwargs["output"]
                assert end_kwargs["usage"]["total_tokens"] == 42

    def test_ut06_api_failure_gen_end_error(self):
        """UT-06: API 失败时 gen.end(level="ERROR") 被调用。"""
        import requests as req_module
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = req_module.HTTPError("500 Server Error")

        mock_span = MagicMock()
        mock_gen = MagicMock()
        mock_span.generation.return_value = mock_gen

        with patch.dict(os.environ, {"MINIMAX_CN_API_KEY": "test-key"}):
            with patch("requests.post", return_value=mock_resp):
                from subgraphs.shared.llm import llm_minimax

                with pytest.raises(req_module.HTTPError):
                    llm_minimax("你好", trace_span=mock_span)

                # 验证 gen.end 被调用，标记 ERROR
                mock_gen.end.assert_called_once()
                end_kwargs = mock_gen.end.call_args[1]
                assert end_kwargs["level"] == "ERROR"
                assert "500" in end_kwargs["status_message"]


class TestObsSpan:
    """UT-07 ~ UT-08: obs_span 上下文管理器。"""

    def test_ut07_normal_span_end_called(self):
        """UT-07: 正常执行时 s.end() 被调用。"""
        from subgraphs.shared.observability import obs_span

        mock_trace = MagicMock()
        mock_s = MagicMock()
        mock_trace.span.return_value = mock_s

        with obs_span(mock_trace, "test/span", metadata={"key": "val"}) as s:
            assert s is mock_s

        # 验证 span 创建参数
        mock_trace.span.assert_called_once_with(name="test/span", metadata={"key": "val"})
        # 验证 end 被调用（无错误参数）
        mock_s.end.assert_called_once_with()

    def test_ut08_exception_span_end_error_and_reraise(self):
        """UT-08: 异常时 s.end(level="ERROR") 被调用，异常继续传播。"""
        from subgraphs.shared.observability import obs_span

        mock_trace = MagicMock()
        mock_s = MagicMock()
        mock_trace.span.return_value = mock_s

        with pytest.raises(ValueError, match="测试异常"):
            with obs_span(mock_trace, "test/error") as s:
                raise ValueError("测试异常")

        # 验证 end 被调用，标记 ERROR
        mock_s.end.assert_called_once_with(status_message="测试异常", level="ERROR")

    def test_obs_span_none_yields_none(self):
        """trace_or_span 为 None 时 yield None，不报错。"""
        from subgraphs.shared.observability import obs_span

        with obs_span(None, "test") as s:
            assert s is None
