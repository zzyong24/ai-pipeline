"""write_book_subgraph 节点实现。

定位：信息调研管道的汇总层。
  aggregate_node: 多来源分析 → 研究综述（保留来源引用）
  write_node:     研究综述 → 参考报告（调研报告格式）
"""
from __future__ import annotations
from typing import Dict, Any

from ..shared.llm import llm_minimax
from ..shared.timeout import with_timeout
from .state import WriteBookState
from .config import WriteBookConfig


def _format_summaries_with_source(summaries: list) -> str:
    """把 summary 列表格式化为带来源标记的文本块。"""
    parts = []
    for i, s in enumerate(summaries):
        title = s.get("title", s.get("video", f"来源{i+1}"))[:60]
        url = s.get("video", "")
        summary = s.get("summary", "")
        parts.append(
            f"【来源 {i+1}】{title}\n"
            f"URL: {url}\n"
            f"{summary}"
        )
    return "\n\n---\n\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# Node 1: aggregate（研究综述）
# ═══════════════════════════════════════════════════════════════════════════
def make_aggregate_node(config: WriteBookConfig):
    """工厂：注入 config，返回 aggregate node。"""

    def aggregate_node(state: WriteBookState) -> Dict[str, Any]:
        summaries = state.get("summaries", [])
        trace_span = state.get("_trace_span")
        print(f"[write_book:aggregate] 研究综述，{len(summaries)} 个来源...")

        if not summaries:
            print("[write_book:aggregate] 无内容，跳过")
            return {"integrated_report": ""}

        sources_text = _format_summaries_with_source(summaries)

        try:
            prompt = f"""你是一个专业的研究分析师。以下是来自 {len(summaries)} 个不同来源的分析报告。

{sources_text}

请生成一份研究综述，要求：

## 跨来源共识
多个来源都认可的核心判断（注明支持来源编号）

## 观点分歧与争议
不同来源之间有分歧的地方，列出各方立场（注明来源编号）

## 独特视角汇总
每个来源提供的独特信息点，其他来源没有涉及的

## 信息空白与不确定性
现有来源未能覆盖或论证不足的问题

## 综合判断
基于所有来源的综合分析结论，标注置信度（高/中/低）

格式要求：用【来源N】标注观点出处，保持客观，不要做价值判断。"""

            integrated = llm_minimax(
                prompt, timeout=max(10, config.timeout_aggregate - 10),
                trace_span=trace_span, generation_name="write_book/aggregate",
            )
            print(f"[write_book:aggregate] 综述完成，长度: {len(integrated)}")
            return {"integrated_report": integrated}

        except TimeoutError as e:
            print(f"[write_book:aggregate] 超时: {e}")
            return {"integrated_report": sources_text}
        except Exception as e:
            print(f"[write_book:aggregate] LLM 失败: {e}")
            return {"integrated_report": sources_text}

    return with_timeout(config.timeout_aggregate)(aggregate_node)


# ═══════════════════════════════════════════════════════════════════════════
# Node 2: write（参考报告）
# ═══════════════════════════════════════════════════════════════════════════
def make_write_node(config: WriteBookConfig):
    """工厂：注入 config，返回 write node。"""

    def write_node(state: WriteBookState) -> Dict[str, Any]:
        topic = state.get("topic", "")
        draft = state.get("integrated_report") or ""
        summaries = state.get("summaries", [])
        trace_span = state.get("_trace_span")
        print(f"[write_book:write] 生成参考报告...")

        if not draft:
            return {"book": f"（主题：{topic}，无可用素材）"}

        # 构建来源列表供报告引用
        source_list = "\n".join(
            f"[{i+1}] {s.get('title', s.get('video',''))[:60]} — {s.get('video','')}"
            for i, s in enumerate(summaries)
        )

        try:
            prompt = f"""你是一名科技领域的深度分析师，正在为专业读者写一篇关于「{topic}」的深度分析文章。

素材来自以下 {len(summaries)} 个信息来源的研究综述：
{draft}

来源清单（供行文中自然引用）：
{source_list}

写作要求：
- 风格：类似虎嗅/36氪的深度报道，或高水平的分析师简报——有观点、有细节、读起来流畅
- 结构：自由选择最适合表达这个话题的结构，不要强行套模板
- 引用方式：自然融入行文，例如"多位业内人士指出""某平台分析显示""有观点认为……但也有声音反驳……"，来源在文末统一列出，不要在正文中插 [N] 脚注
- 多视角：有分歧的地方自然呈现不同声音，不要回避争议，但也不要为了呈现争议而刻意制造对立
- 长度：不少于 {config.min_words} 字，内容要有密度，不要用空洞的过渡句填充
- 禁止：不要用"综上所述""本文分析""研究显示""值得注意的是"等套话，不要在文末加"结语"或"总结"段落重复已说过的内容
- 文末附"参考来源"列表，格式：标题 — URL

直接开始写文章正文。"""

            book = llm_minimax(
                prompt, timeout=max(10, config.timeout_write - 10),
                trace_span=trace_span, generation_name="write_book/write",
            )
            print(f"[write_book:write] 报告完成，长度: {len(book)}")
            return {"book": book, "error": None}

        except TimeoutError as e:
            print(f"[write_book:write] 超时: {e}")
            return {"book": draft, "error": f"write timeout: {e}"}
        except Exception as e:
            print(f"[write_book:write] 失败: {e}")
            return {"book": draft, "error": f"write failed: {e}"}

    return with_timeout(config.timeout_write)(write_node)
