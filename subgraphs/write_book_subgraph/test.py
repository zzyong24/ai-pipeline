"""write_book_subgraph 独立测试。

用法：
    python -m subgraphs.write_book_subgraph.test

会用 mock 摘要数据跑一遍聚合+写书流程。
"""
from __future__ import annotations

from . import build_write_book_subgraph
from .config import WriteBookConfig


MOCK_SUMMARIES = [
    {
        "video": "https://example.com/v1",
        "title": "AI Agent 入门",
        "summary": "介绍了 Agent 的三要素：大脑、工具、循环。强调工具调用的准确性是 Agent 成败关键。",
    },
    {
        "video": "https://example.com/v2",
        "title": "2026 LangGraph 生态",
        "summary": "LangGraph 成为 AI Agent 编排事实标准，SubGraph 模式支持组件级复用。",
    },
    {
        "video": "https://example.com/v3",
        "title": "上下文工程实践",
        "summary": "Context Engineering 取代 Prompt Engineering 成为 2026 关键词。",
    },
]


def main():
    print(f"\n━━━━━━ write_book_subgraph 独立测试 ━━━━━━")
    print(f"摘要数：{len(MOCK_SUMMARIES)}\n")

    subgraph = build_write_book_subgraph(
        WriteBookConfig(timeout_aggregate=120, timeout_write=180, min_chapters=3, min_words=800)
    )

    result = subgraph.invoke({"topic": "AI Agent 发展", "summaries": MOCK_SUMMARIES})

    print("\n━━━━━━ 结果 ━━━━━━")
    print(f"error: {result.get('error')}")
    print(f"integrated_report 长度: {len(result.get('integrated_report') or '')}")
    print(f"book 长度: {len(result.get('book') or '')}")
    print(f"\nbook 前 500 字:")
    print((result.get("book") or "")[:500])


if __name__ == "__main__":
    main()
