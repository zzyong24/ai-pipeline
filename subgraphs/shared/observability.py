"""
Langfuse 可观测封装（v4 最佳实践）。

Langfuse v4 推荐接入方式：
1. @observe 装饰器 —— 包裹函数，自动捕获输入/输出/耗时/错误
2. LangChain CallbackHandler —— 传给 LangGraph graph.invoke() 的 config，
   自动捕获所有节点、LLM 调用的 trace

最简用法（run_pipeline 已内置）：
    LANGFUSE_PUBLIC_KEY=pk-lf-xxx
    LANGFUSE_SECRET_KEY=sk-lf-xxx
    LANGFUSE_BASE_URL=http://localhost:3001
    → 跑 Pipeline 后打开 Langfuse UI 即可看到完整 trace
"""
from __future__ import annotations
import os
from contextlib import contextmanager
from typing import Optional, Any


# ─────────────────────────────────────────────────────────────────────────────
# 核心 1：LangChain CallbackHandler（LangGraph 自动全链路 trace）
# ─────────────────────────────────────────────────────────────────────────────

def get_langfuse_callback(trace_id: Optional[str] = None):
    """
    返回 Langfuse LangChain CallbackHandler。
    传入 LangGraph graph.invoke() 的 config["callbacks"]，
    自动 trace 所有节点执行和 LLM 调用。

    Args:
        trace_id: 可选，关联到 @observe 创建的父 trace ID

    用法：
        handler = get_langfuse_callback(trace_id=current_trace_id)
        config = {"callbacks": [handler]} if handler else {}
        graph.invoke(state, {**graph_config, **config})
    """
    try:
        if not os.environ.get("LANGFUSE_PUBLIC_KEY"):
            return None
        from langfuse.langchain import CallbackHandler
        if trace_id:
            return CallbackHandler(trace_context={"trace_id": trace_id})
        return CallbackHandler()
    except ImportError:
        return None
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 核心 2：@observe 装饰器（为 Pipeline 入口创建顶层 trace）
# ─────────────────────────────────────────────────────────────────────────────

def get_observe_decorator(name: Optional[str] = None, as_type: Optional[str] = None):
    """
    返回 Langfuse @observe 装饰器。
    未配置时返回 identity 装饰器，不影响函数行为。

    用法：
        @get_observe_decorator(name="video-md-pipeline", as_type="span")
        def run_pipeline(...): ...
    """
    try:
        if not os.environ.get("LANGFUSE_PUBLIC_KEY"):
            return _identity_decorator
        from langfuse import observe
        kwargs: dict = {}
        if name:
            kwargs["name"] = name
        if as_type:
            kwargs["as_type"] = as_type
        return observe(**kwargs) if kwargs else observe
    except ImportError:
        return _identity_decorator
    except Exception:
        return _identity_decorator


def _identity_decorator(func):
    """什么都不做的装饰器，Langfuse 未配置时的降级。"""
    return func


# ─────────────────────────────────────────────────────────────────────────────
# 辅助：获取当前 trace ID（用于关联 CallbackHandler）
# ─────────────────────────────────────────────────────────────────────────────

def get_current_trace_id() -> Optional[str]:
    """
    获取当前 @observe 上下文中的 trace ID。
    在 @observe 装饰的函数内部调用，用于把 trace_id 传给 CallbackHandler。
    未配置或不在 @observe 上下文中时返回 None。
    """
    try:
        if not os.environ.get("LANGFUSE_PUBLIC_KEY"):
            return None
        from langfuse import get_client
        return get_client().get_current_trace_id()
    except Exception:
        return None


def update_current_trace(session_id: Optional[str] = None,
                          metadata: Optional[dict] = None,
                          tags: Optional[list] = None):
    """
    在 @observe 上下文中更新当前 trace 的元数据（session_id、tags 等）。
    在 @observe 装饰的函数内部调用。未配置时静默跳过。
    """
    try:
        if not os.environ.get("LANGFUSE_PUBLIC_KEY"):
            return
        from langfuse import get_client
        kwargs: dict = {}
        if session_id:
            kwargs["session_id"] = session_id
        if metadata:
            kwargs["metadata"] = metadata
        if tags:
            kwargs["tags"] = tags
        if kwargs:
            get_client().update_current_span(**kwargs)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# 辅助：flush（确保数据上报，在 Pipeline 结束时调用）
# ─────────────────────────────────────────────────────────────────────────────

def flush():
    """
    刷新所有待上报的 Langfuse 数据。
    在 Pipeline 结束时调用，确保 trace 完整上报。
    未配置时静默跳过。
    """
    try:
        if not os.environ.get("LANGFUSE_PUBLIC_KEY"):
            return
        from langfuse import get_client
        get_client().flush()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# 向后兼容：保留旧接口（旧代码不受影响）
# ─────────────────────────────────────────────────────────────────────────────

def get_langfuse():
    """[已废弃] 返回 Langfuse 客户端。v4 推荐用 get_observe_decorator + get_langfuse_callback。"""
    try:
        if not os.environ.get("LANGFUSE_PUBLIC_KEY"):
            return None
        from langfuse import get_client
        return get_client()
    except Exception:
        return None


def create_trace(name: str, session_id: str, metadata: dict = None):
    """[已废弃] v4 推荐用 @observe 装饰器 + CallbackHandler。"""
    return None


def obs_span(trace_or_span=None, name: str = "", metadata: dict = None):
    """[已废弃] v4 推荐用 @observe 装饰器 + CallbackHandler。"""
    @contextmanager
    def _noop():
        yield None
    return _noop()


def flush_trace(trace=None):
    """[已废弃] 请用 flush()。"""
    flush()
