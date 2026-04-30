"""
Langfuse 可观测封装。

设计原则：
- 懒加载：get_langfuse() 未配置时返回 None，不阻塞运行
- None 安全：所有函数接收 None 时静默跳过，不报错
- 向后兼容：现有代码不需要改动，trace_span=None 就是无埋点模式
"""
from __future__ import annotations
import os
from contextlib import contextmanager
from typing import Optional, Any


def get_langfuse():
    """懒加载 Langfuse 客户端。LANGFUSE_PUBLIC_KEY 未设置时返回 None。"""
    try:
        if not os.environ.get("LANGFUSE_PUBLIC_KEY"):
            return None
        from langfuse import Langfuse
        return Langfuse()
    except ImportError:
        return None
    except Exception:
        return None


def create_trace(name: str, session_id: str, metadata: dict = None):
    """创建顶层 trace（Pipeline 级别）。未配置时返回 None。"""
    lf = get_langfuse()
    if lf is None:
        return None
    try:
        return lf.trace(name=name, session_id=session_id, metadata=metadata or {})
    except Exception:
        return None


@contextmanager
def obs_span(trace_or_span, name: str, metadata: dict = None):
    """SubGraph 级别 span 上下文管理器。trace_or_span 为 None 时 yield None。"""
    if trace_or_span is None:
        yield None
        return
    s = None
    try:
        s = trace_or_span.span(name=name, metadata=metadata or {})
        yield s
        s.end()
    except Exception as e:
        if s:
            try:
                s.end(status_message=str(e), level="ERROR")
            except Exception:
                pass
        raise


def flush_trace(trace):
    """刷新 trace，确保数据上报。trace 为 None 时静默跳过。"""
    if trace is None:
        return
    try:
        lf = get_langfuse()
        if lf:
            lf.flush()
    except Exception:
        pass
