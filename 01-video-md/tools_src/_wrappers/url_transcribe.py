#!/usr/bin/env python3
"""n8n Execute Command wrapper: video-url-transcribe
接收 JSON 字符串参数，输出 JSON 结果供 n8n 后续节点使用。
"""
import sys
import json
import os
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from video_url_transcriber import video_url_transcribe


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="视频 URL")
    parser.add_argument("--output-dir", default="/tmp", help="输出目录")
    parser.add_argument("--quality", default="audio_only",
                        choices=["audio_only", "best"],
                        help="audio_only | best")
    args = parser.parse_args()

    # BILIBILI_COOKIE_FILE 环境变量透传
    cookie = os.environ.get("BILIBILI_COOKIE_FILE", "")
    if cookie:
        print(f"🔑 B站 Cookie 文件: {cookie}", file=sys.stderr)

    print(f"⬇️ 下载中: {args.url}", file=sys.stderr)
    result = video_url_transcribe(args.url, args.output_dir, quality=args.quality)
    print(f"✅ 转录完成: {result['srt_path']}", file=sys.stderr)

    # n8n 读取 stdout JSON
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
