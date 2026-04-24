"""research_subgraph 独立测试。

用法：
    python -m subgraphs.research_subgraph.test "你要研究的主题"

必须设置环境变量：
    MINIMAX_CN_API_KEY
"""
from __future__ import annotations
import sys
import json

from . import build_research_subgraph
from .config import ResearchConfig


def main():
    topic = sys.argv[1] if len(sys.argv) > 1 else "AI Agent 发展趋势"

    print(f"\n━━━━━━ research_subgraph 独立测试 ━━━━━━")
    print(f"主题：{topic}\n")

    subgraph = build_research_subgraph(ResearchConfig(timeout=60))
    result = subgraph.invoke({"topic": topic})

    print("\n━━━━━━ 结果 ━━━━━━")
    print(f"错误：{result.get('error')}")
    print(f"URL 数量：{len(result.get('video_urls', []))}")
    print(f"URL 列表：")
    for u in result.get("video_urls", []):
        print(f"  - {u}")
    print(f"\n原始 selected_videos：")
    print(json.dumps(result.get("selected_videos", []), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
