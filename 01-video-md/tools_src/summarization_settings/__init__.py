"""summarization-settings — 获取/修改 msg-collect 总结配置"""
import os
import requests
from typing import Optional

_MSGCOLLECT_BASE = os.environ.get("MSG_COLLECT_BASE", "http://127.0.0.1:8000")


def get_settings() -> dict:
    """获取当前 summarization 配置"""
    resp = requests.get(f"{_MSGCOLLECT_BASE}/summarization/settings", timeout=10)
    resp.raise_for_status()
    return resp.json()


def update_settings(
    mode: Optional[str] = None,
    enable_summarization: Optional[bool] = None,
    **kwargs,
) -> dict:
    """
    修改 summarization 配置。

    Args:
        mode: "standard" | "agent" | "auto"
        enable_summarization: True/False
        其他参数: chunk_target_duration_sec, llm_call_retry_max, ...
    """
    payload = {k: v for k, v in kwargs.items() if v is not None}
    if mode is not None:
        payload["mode"] = mode
    if enable_summarization is not None:
        payload["enable_summarization"] = enable_summarization

    resp = requests.put(
        f"{_MSGCOLLECT_BASE}/summarization/settings",
        json=payload,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()
