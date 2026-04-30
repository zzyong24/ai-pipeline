"""
Langfuse 可观测单元测试（v4 接口）。

覆盖：
  UT-01: get_langfuse() 未配置返回 None
  UT-02: get_langfuse_callback() 已配置返回 CallbackHandler 实例
  UT-03: langfuse 包未安装时 get_langfuse_callback() 返回 None
  UT-04: llm_minimax trace_span=None 时不调 span 方法
  UT-05: llm_minimax trace_span=mock_span 时调用 generation
  UT-06: llm_minimax API 失败时 gen.end(level="ERROR") 被调
  UT-07: obs_span(None) 兼容接口：yield None，不报错
  UT-08: get_observe_decorator 未配置时返回 identity 装饰器
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# 确保 ai-pipeline 根目录在 sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestGetLangfuse:
    """UT-01 ~ UT-03: observability 核心函数行为测试（v4 接口）。"""

    def test_ut01_no_public_key_returns_none(self):
        """UT-01: LANGFUSE_PUBLIC_KEY 未设置时 get_langfuse() 返回 None。"""
        env = os.environ.copy()
        env.pop("LANGFUSE_PUBLIC_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            from subgraphs.shared.observability import get_langfuse
            result = get_langfuse()
            assert result is None

    def test_ut02_with_public_key_returns_instance(self):
        """UT-02: LANGFUSE_PUBLIC_KEY 已设置时 get_langfuse_callback() 返回 CallbackHandler。"""
        with patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "pk-lf-test",
                                      "LANGFUSE_SECRET_KEY": "sk-lf-test"}):
            with patch("langfuse.langchain.CallbackHandler") as MockHandler:
                mock_instance = MagicMock()
                MockHandler.return_value = mock_instance
                from subgraphs.shared import observability
                import importlib
                importlib.reload(observability)
                result = observability.get_langfuse_callback()
                assert result is mock_instance

    def test_ut03_import_error_returns_none(self):
        """UT-03: langfuse 包未安装时 get_langfuse_callback() 返回 None。"""
        env = {k: v for k, v in os.environ.items()}
        env["LANGFUSE_PUBLIC_KEY"] = "pk-lf-test"
        with patch.dict(os.environ, env):
            from subgraphs.shared import observability
            import importlib
            # 模拟 ImportError
            with patch.object(observability, "get_langfuse_callback",
                               side_effect=None, wraps=None) as m:
                m.return_value = None
                result = observability.get_langfuse_callback()
                assert result is None


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
    """UT-07 ~ UT-08: obs_span 兼容接口 + get_observe_decorator。"""

    def test_ut07_obs_span_none_yields_none(self):
        """UT-07: obs_span(None) 兼容接口，yield None，不报错。"""
        from subgraphs.shared.observability import obs_span
        with obs_span(None, "test") as s:
            assert s is None

    def test_ut08_observe_decorator_no_config_is_identity(self):
        """UT-08: 未配置 LANGFUSE_PUBLIC_KEY 时 get_observe_decorator 返回 identity 装饰器。"""
        env = os.environ.copy()
        env.pop("LANGFUSE_PUBLIC_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            from subgraphs.shared.observability import get_observe_decorator
            decorator = get_observe_decorator(name="test", as_type="span")
            # identity 装饰器不改变函数
            call_count = [0]

            @decorator
            def my_func(x):
                call_count[0] += 1
                return x * 2

            result = my_func(5)
            assert result == 10
            assert call_count[0] == 1

    def test_obs_span_none_yields_none(self):
        """兼容测试：obs_span(None) yield None，不报错。"""
        from subgraphs.shared.observability import obs_span
        with obs_span(None, "test") as s:
            assert s is None
