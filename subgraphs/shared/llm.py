"""
LLM 客户端封装 — MiniMax

用法：
    from subgraphs.shared.llm import llm_minimax
    text = llm_minimax("你好", timeout=120)

不读环境变量（放在调用时），不维护会话状态。
"""
from __future__ import annotations
import os
import re


def llm_minimax(prompt: str, model: str = "MiniMax-M2", timeout: int = 120) -> str:
    """调用 MiniMax 生成文本。

    Args:
        prompt: 用户 prompt
        model: 模型名，默认 MiniMax-M2
        timeout: 请求超时秒数

    Returns:
        清理后的文本（去除 {{ }} 占位符）

    Raises:
        RuntimeError: MINIMAX_CN_API_KEY 未设置
    """
    key = os.environ.get("MINIMAX_CN_API_KEY", "")
    if not key:
        raise RuntimeError("MINIMAX_CN_API_KEY 环境变量未设置")

    import requests
    resp = requests.post(
        "https://api.minimax.chat/v1/text/chatcompletion_v2",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"].get("content") or ""
    return re.sub(r"\{\{[\s\S]*?\}\}", "", raw).strip()
