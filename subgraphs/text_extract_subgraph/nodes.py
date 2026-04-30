"""text_extract_subgraph 节点实现。
处理非视频文本内容（推文/文章/帖子），直接生成结构化 summary。
与 whisper_summarizer 输出格式一致，可直接进入 write_book 汇总层。
"""
from __future__ import annotations
from typing import Dict, Any
from ..shared.llm import llm_minimax
from ..shared.timeout import with_timeout
from .state import TextExtractState
from .config import TextExtractConfig


def make_extract_node(config: TextExtractConfig):
    def extract_node(state: TextExtractState) -> Dict[str, Any]:
        source_type = state.get("source_type", "unknown")
        url = state.get("source_url", "")
        title = state.get("title", "")
        text = state.get("text_content", "")[:config.max_content_chars]
        author = state.get("author", "")
        topic = state.get("topic", "")
        trace_span = state.get("_trace_span")

        print(f"[text_extract:{source_type}] 提炼: {title[:40]}...")

        if not text and not title:
            return {"summary": None, "error": "无内容可分析"}

        content_desc = {
            "twitter": "X/Twitter 推文",
            "hackernews": "Hacker News 帖子",
            "zhihu": "知乎内容",
        }.get(source_type, "网络内容")

        prompt = f"""你是一个专业的信息分析师，正在为研究者整理内容来源。以下是一篇{content_desc}。

请从调研视角提炼，输出格式严格如下：

## 核心主张（一句话）
这个内容最核心的判断或结论是什么？

## 关键论点（2-4条）
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

---
来源平台：{content_desc}
作者：{author or "未知"}
标题：{title}
内容：
{text}

注意：不要输出行动项、学习建议或操作指南，只做客观分析。"""

        try:
            summary = llm_minimax(
                prompt, timeout=max(10, config.timeout - 10),
                trace_span=trace_span, generation_name=f"text_extract/{source_type}",
            )
            print(f"[text_extract:{source_type}] 完成，长度: {len(summary)}")
            return {"summary": summary, "error": None}
        except Exception as e:
            print(f"[text_extract:{source_type}] 失败: {e}")
            return {"summary": None, "error": str(e)}

    return with_timeout(config.timeout)(extract_node)
