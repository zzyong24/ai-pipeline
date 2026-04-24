#!/usr/bin/env python3
"""audio-transcribe CLI — n8n Execute Command 调用入口"""
import sys
import json
from pathlib import Path
from audio_transcribe import transcribe
import argparse

def main():
    parser = argparse.ArgumentParser(description="音频转字幕")
    parser.add_argument("audio_path", help="本地音频文件路径")
    parser.add_argument("-o", "--output", default=".", help="输出目录")
    parser.add_argument("--model", default="base", choices=["tiny", "base", "small", "medium"])
    args = parser.parse_args()

    result = transcribe(args.audio_path, args.output)
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
