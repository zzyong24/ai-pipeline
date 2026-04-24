"""CLI: whisper-summarize"""
import argparse
import sys
from whisper_summarizer import summarize


def main():
    parser = argparse.ArgumentParser(description="字幕文件 → LLM 结构化总结")
    parser.add_argument("subtitle", help="SRT 或 TXT 字幕文件路径")
    parser.add_argument("-o", "--output", help="输出 Markdown 文件路径")
    args = parser.parse_args()

    try:
        result = summarize(args.subtitle, args.output)
        print(f"✅ 总结已生成")
        if result.get("output_path"):
            print(f"📄 {result['output_path']}")
        print("\n" + result["summary"])
    except Exception as e:
        print(f"❌ 错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
