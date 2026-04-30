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
            prompt = f"""你是一个专业的内容整合专家。请将以下多个视频的总结整合成一份结构化的综合报告：

{summaries_text}

请按以下格式输出：
## 综合主题
## 核心观点（按主题分类）
## 各部分详细内容
## 行动建议

只需返回报告正文。"""

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
            prompt = f"""你是一个专业作家。请将以下草稿扩展成一本结构完整、内容翔实的电子书。

主题：{topic}

草稿：
{draft}

请生成书籍目录结构和各章节详细内容，至少 {config.min_chapters} 章，每章有实质性内容。总字数不少于 {config.min_words} 字。只需返回书籍正文。"""

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
