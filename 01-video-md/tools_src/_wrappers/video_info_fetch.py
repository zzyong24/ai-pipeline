#!/usr/bin/env python3
"""n8n Execute Command wrapper: video-info-fetch"""
import sys
import json
import argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from video_info_fetcher import fetch_video_info

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    args = parser.parse_args()
    result = fetch_video_info(args.url)
    print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    main()
