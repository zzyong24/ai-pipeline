#!/usr/bin/env python3
"""video-download CLI — n8n Execute Command 调用入口"""
import sys
import json
import argparse

from video_download import download


def main():
    parser = argparse.ArgumentParser(description="视频下载工具 v2（字幕优先 + yt_dlp Python API）")
    parser.add_argument("url", help="视频 URL")
    parser.add_argument("-o", "--output", default=".", help="输出目录（默认当前目录）")
    parser.add_argument("--quality", default="audio_only", choices=["audio_only", "best"])
    parser.add_argument("--sessdata", default="", help="B站 SESSDATA cookie（用于字幕直取）")
    parser.add_argument("--subtitle-only", action="store_true", help="仅提取字幕，不下载视频")
    args = parser.parse_args()

    result = download(
        args.url,
        output_dir=args.output,
        quality=args.quality,
        sessdata=args.sessdata,
        subtitle_only=args.subtitle_only,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("success", False) else 1)


if __name__ == "__main__":
    main()
