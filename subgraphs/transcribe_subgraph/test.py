"""transcribe_subgraph 独立测试。

用法：
    python -m subgraphs.transcribe_subgraph.test "https://www.bilibili.com/video/BV..."

依赖：
    - tools_src 目录（含 video_download / audio_transcribe / whisper_summarizer）
    - MINIMAX_CN_API_KEY
"""
from __future__ import annotations
import sys
from pathlib import Path

from . import build_transcribe_subgraph
from .config import TranscribeConfig


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.bilibili.com/video/BV1GJ411x7h7/"

    # 假设测试时在 ai-pipeline/ 目录运行
    tools_src = Path("01-video-md/tools_src").resolve()
    output_base = Path("/tmp/transcribe_test_output")

    config = TranscribeConfig(
        output_base=output_base,
        tools_src=tools_src,
    )

    subgraph = build_transcribe_subgraph(config)

    print(f"\n━━━━━━ transcribe_subgraph 独立测试 ━━━━━━")
    print(f"URL: {url}")
    print(f"输出: {output_base}/task-0/\n")

    result = subgraph.invoke({
        "video_url": url,
        "task_idx": 0,
        "topic": "test",
    })

    print("\n━━━━━━ 结果 ━━━━━━")
    print(f"success: {result.get('success')}")
    print(f"error:   {result.get('error')}")
    print(f"title:   {result.get('title')}")
    print(f"srt:     {result.get('srt_path')}")
    print(f"summary: {(result.get('summary') or '')[:200]}...")


if __name__ == "__main__":
    main()
