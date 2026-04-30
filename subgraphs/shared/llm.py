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


def llm_minimax(prompt: str, model: str = "MiniMax-M2", timeout: int = 120,
                trace_span=None, generation_name: str = "llm_minimax") -> str:
    """调用 MiniMax 生成文本。

    Args:
        prompt: 用户 prompt
        model: 模型名，默认 MiniMax-M2
        timeout: 请求超时秒数
        trace_span: Langfuse trace/span 对象，None 时不埋点
        generation_name: generation 名称，用于 Langfuse 展示

    Returns:
        清理后的文本（去除 {{ }} 占位符）

    Raises:
        RuntimeError: MINIMAX_CN_API_KEY 未设置
    """
    key = os.environ.get("MINIMAX_CN_API_KEY", "")
    if not key:
        raise RuntimeError("MINIMAX_CN_API_KEY 环境变量未设置")

    # 创建 Langfuse generation（若 trace_span 可用）
    gen = None
    if trace_span is not None:
        try:
            gen = trace_span.generation(
                name=generation_name,
                model=model,
                input=prompt[:2000],
            )
        except Exception:
            gen = None

    import requests
    try:
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
        data = resp.json()
        raw = data["choices"][0]["message"].get("content") or ""
        result = re.sub(r"\{\{[\s\S]*?\}\}", "", raw).strip()

        # 记录成功的 generation
        if gen is not None:
            try:
                usage = data.get("usage", {})
                gen.end(
                    output=result[:2000],
                    usage={"total_tokens": usage.get("total_tokens", 0)},
                )
            except Exception:
                pass

        return result

    except Exception as e:
        # 记录失败的 generation
        if gen is not None:
            try:
                gen.end(status_message=str(e), level="ERROR")
            except Exception:
                pass
        raise
