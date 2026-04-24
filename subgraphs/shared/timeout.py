"""
超时装饰器：给任意函数加超时，超时视为失败。

用法：
    @with_timeout(120)
    def my_slow_fn():
        ...
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError


def with_timeout(timeout_seconds: int):
    """给任意函数加超时，被 TimeoutError 视为失败。

    Args:
        timeout_seconds: 超时秒数

    Raises:
        TimeoutError: 执行超过 timeout_seconds
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            with ThreadPoolExecutor(max_workers=1) as exc:
                future = exc.submit(func, *args, **kwargs)
                try:
                    return future.result(timeout=timeout_seconds)
                except FuturesTimeoutError:
                    raise TimeoutError(
                        f"[{func.__name__}] 执行超时（{timeout_seconds}s）"
                    )
        return wrapper
    return decorator
