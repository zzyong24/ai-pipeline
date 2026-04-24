#!/usr/bin/env python3
"""n8n 编排 wrapper：接收 JSON 输入，依次调用 video_transcriber + whisper_summarizer"""
import sys, json, os, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video-path", required=True)
    parser.add_argument("--output-dir", default="/tmp")
    parser.add_argument("--minimax-key", default=None)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: video-transcribe
    from video_transcriber import transcribe
    print("🔄 转录中...", file=sys.stderr)
    result = transcribe(args.video_path, str(output_dir))
    srt_path = result["srt"]
    print(f"✅ 转录完成: {srt_path}", file=sys.stderr)

    # Step 2: whisper-summarize
    if args.minimax_key:
        os.environ["MINIMAX_CN_API_KEY"] = args.minimax_key
    elif not os.environ.get("MINIMAX_CN_API_KEY"):
        key = os.environ.get("MINIMAX_CN_API_KEY", "")
        os.environ["MINIMAX_CN_API_KEY"] = key

    from whisper_summarizer import summarize
    print("🔄 总结中...", file=sys.stderr)
    summary_path = str(output_dir / "AI总结.md")
    summary_result = summarize(srt_path, summary_path)
    print(f"✅ 总结完成: {summary_path}", file=sys.stderr)

    # 输出 JSON 给 n8n
    output = {
        "srt_path": srt_path,
        "vtt_path": result["vtt"],
        "txt_path": result["txt"],
        "summary_path": summary_path,
        "summary_preview": summary_result["summary"][:200],
    }
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
