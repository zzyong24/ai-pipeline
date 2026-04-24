#!/usr/bin/env python3
"""CLI: video-info-fetch <B站URL>"""
import argparse
import sys
import json
from video_info_fetcher import fetch_video_info


def main():
    parser = argparse.ArgumentParser(description="获取 B 站视频信息（是否多P、分P列表）")
    parser.add_argument("url", help="B 站视频链接（BV号/b23.tv/完整链接）")
    args = parser.parse_args()

    try:
        result = fetch_video_info(args.url)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"❌ 错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
