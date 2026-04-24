"""llm-connection-tester — 测试 MiniMax LLM 连接是否可用"""
import os
import requests

_MSGCOLLECT_BASE = os.environ.get("MSG_COLLECT_BASE", "http://127.0.0.1:8000")


def test_connection(provider: str = "minimax") -> dict:
    """
    测试 LLM 连接。

    Returns:
        {
            "status": "ok" | "error",
            "message": str,
            "response": str | None,
            "latency_ms": float | None,
        }
    """
    try:
        resp = requests.post(f"{_MSGCOLLECT_BASE}/llm/test", timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return {
            "status": "ok" if data.get("status") == "ok" else "error",
            "message": data.get("message", ""),
            "response": data.get("response"),
        }
    except requests.exceptions.ConnectionError:
        return {
            "status": "error",
            "message": f"无法连接到 msg-collect ({_MSGCOLLECT_BASE})，请确认服务已启动",
            "response": None,
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "response": None,
        }
