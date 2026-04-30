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

        prompt = f"""你是一个专业的信息分析师，正在为研究者整理内容来源。以下是一个视频的字幕内容。

请从调研视角提炼，输出格式严格如下：

## 核心主张（一句话）
这个视频/内容最核心的判断或结论是什么？

## 关键论点（3-5条）
作者提出的主要论据，每条注明推理依据（数据/案例/逻辑）

## 作者立场与视角
- 作者背景/身份（如能判断）：
- 观点倾向（乐观/悲观/中立/批判）：
- 潜在局限或偏见：

## 可信度评估
- 有具体数据/案例支撑：是/否
- 论点可验证性：高/中/低
- 与主流观点的异同：

## 独特信息点
其他来源不常见、值得重点记录的信息

字幕内容：
{full_text}

注意：不要输出行动项、学习建议或操作指南，只做客观分析。"""

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
