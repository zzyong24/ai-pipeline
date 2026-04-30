"""write_book_subgraph 节点实现。

两个 node：
  aggregate_node: 多摘要 → 综合报告
  write_node:     综合报告 → 完整书稿
"""
from __future__ import annotations
from typing import Dict, Any

from ..shared.llm import llm_minimax
from ..shared.timeout import with_timeout
from .state import WriteBookState
from .config import WriteBookConfig


def _format_summaries(summaries: list) -> str:
    """把 summary 列表拼成可阅读的文本块（纯函数）。"""
    return "\n\n".join(
        f"=== 视频 {i+1}: {s.get('video', '')[:50]} ===\n{s.get('summary', '')}"
        for i, s in enumerate(summaries)
    )


# ═══════════════════════════════════════════════════════════════════════════
# Node 1: aggregate
# ═══════════════════════════════════════════════════════════════════════════
def make_aggregate_node(config: WriteBookConfig):
    """工厂：注入 config，返回 aggregate node。"""

    def aggregate_node(state: WriteBookState) -> Dict[str, Any]:
        summaries = state.get("summaries", [])
        trace_span = state.get("_trace_span")
        print(f"[write_book:aggregate] 整合 {len(summaries)} 个视频摘要...")

        if not summaries:
            print("[write_book:aggregate] 无摘要内容，跳过")
            return {"integrated_report": ""}

        summaries_text = _format_summaries(summaries)

        try:
            prompt = f"""你是一个专业的内容整合专家。以下是多个视频的内容摘要，请整合成一份结构清晰的综合分析：

{summaries_text}

输出格式：
## 核心主题
## 关键洞察（跨视频提炼，不要重复各视频的摘要）
## 各角度详细分析
## 可落地的行动建议

直接输出内容，不要加任何元说明（如"以下是报告"之类的话）。"""

            integrated = llm_minimax(
                prompt, timeout=max(10, config.timeout_aggregate - 10),
                trace_span=trace_span, generation_name="write_book/aggregate",
            )
            print(f"[write_book:aggregate] 整合完成，长度: {len(integrated)}")
            return {"integrated_report": integrated}

        except TimeoutError as e:
            print(f"[write_book:aggregate] 超时: {e}，使用原始摘要代替")
            return {"integrated_report": summaries_text}
        except Exception as e:
            print(f"[write_book:aggregate] LLM 失败: {e}")
            return {"integrated_report": summaries_text}

    # 用装饰器给整个 node 加外层超时兜底
    return with_timeout(config.timeout_aggregate)(aggregate_node)


# ═══════════════════════════════════════════════════════════════════════════
# Node 2: write
# ═══════════════════════════════════════════════════════════════════════════
def make_write_node(config: WriteBookConfig):
    """工厂：注入 config，返回 write node。"""

    def write_node(state: WriteBookState) -> Dict[str, Any]:
        topic = state.get("topic", "")
        draft = state.get("integrated_report") or ""
        trace_span = state.get("_trace_span")
        print(f"[write_book:write] 生成书稿...")

        if not draft:
            # 占位书稿
            return {"book": f"（主题：{topic}，无可用摘要，内容待补充）"}

        try:
            prompt = f"""基于以下内容草稿，围绕主题「{topic}」生成一份结构完整、内容充实的深度分析文档。

草稿：
{draft}

要求：
- 至少 {config.min_chapters} 个主要章节，每章有实质性内容
- 总字数不少于 {config.min_words} 字
- 行文直接，聚焦洞察和分析，不要用"本文""本文档""笔者"等自我指涉表达
- 直接输出文档正文，不要加前言或元说明"""

            book = llm_minimax(
                prompt, timeout=max(10, config.timeout_write - 10),
                trace_span=trace_span, generation_name="write_book/write",
            )
            print(f"[write_book:write] 书稿完成，长度: {len(book)}")
            return {"book": book, "error": None}

        except TimeoutError as e:
            print(f"[write_book:write] 超时: {e}，使用草稿代替")
            return {"book": draft, "error": f"write timeout: {e}"}
        except Exception as e:
            print(f"[write_book:write] 失败: {e}")
            return {"book": draft, "error": f"write failed: {e}"}

    return with_timeout(config.timeout_write)(write_node)
