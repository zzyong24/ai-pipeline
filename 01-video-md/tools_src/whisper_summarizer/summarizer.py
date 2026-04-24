"""字幕总结工具 — 读取 SRT/TXT，直调 MiniMax API 生成结构化总结"""

import os
import re
import requests
from pathlib import Path


def _strip_thinking_blocks(text: str) -> str:
    """剥掉 {{...}} thinking 块"""
    return re.sub(r"\{\{[\s\S]*?\}\}", "", text).strip()


def _summarize_via_minimax(prompt: str, api_key: str) -> str:
    """直调 MiniMax-M2 API，禁用 reasoning_content，返回干净文本"""
    resp = requests.post(
        "https://api.minimax.chat/v1/text/chatcompletion_v2",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "MiniMax-M2",
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    msg = data["choices"][0]["message"]
    # MiniMax-M2 返回字段：
    #   content           — 最终回复（可能含 {{...}} thinking 块）
    #   reasoning_content — 推理过程（弃用，统一走 content 里的 thinking 块）
    raw = msg.get("content") or ""
    return _strip_thinking_blocks(raw)


class WhisperSummarizer:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("MINIMAX_CN_API_KEY", "")
        if not self.api_key:
            raise ValueError("需要 MINIMAX_CN_API_KEY 环境变量")

    def summarize(self, subtitle_path: str, output_path: str = None) -> dict:
        sub_path = Path(subtitle_path)
        with open(sub_path, "r", encoding="utf-8") as f:
            raw = f.read()

        # 提取纯文本（去掉 SRT 序号、HTML 标签和时间轴）
        lines = []
        for line in raw.split("\n"):
            line = line.strip()
            if not line:
                continue
            if "-->" in line:
                continue
            if line.isdigit():
                continue
            # 去掉 HTML 标签
            line = re.sub(r"<[^>]+>", "", line)
            if line:
                lines.append(line)
        full_text = "\n".join(lines)

        # 截断防止超出 token 上限（取前 8000 字符，约 2000 tokens）
        if len(full_text) > 8000:
            full_text = full_text[:8000] + "\n[...截断...]"

        prompt = f"""请总结以下字幕内容，生成结构化笔记，包含：
- 核心主题（一句话）
- 关键观点（3-5条）
- 重要细节
- 行动项（如果有）

字幕内容：
{full_text}"""

        summary = _summarize_via_minimax(prompt, self.api_key)

        result = {"summary": summary, "summary_length": len(summary)}
        if output_path:
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(summary, encoding="utf-8")
            result["output_path"] = str(out)
        return result


def summarize(subtitle_path: str, output_path: str = None) -> dict:
    """CLI 封装"""
    return WhisperSummarizer().summarize(subtitle_path, output_path)
