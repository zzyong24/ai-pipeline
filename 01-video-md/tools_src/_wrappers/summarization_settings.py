#!/usr/bin/env python3
"""n8n Execute Command wrapper: summarization-settings"""
import sys
import json
import argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from summarization_settings import get_settings, update_settings

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["get", "set"])
    parser.add_argument("--enable-summarization", type=lambda x: x.lower() == "true",
                        metavar="true|false")
    parser.add_argument("--mode", choices=["standard", "agent", "auto"])
    args = parser.parse_args()

    if args.action == "get":
        result = get_settings()
    else:
        kwargs = {}
        if args.enable_summarization is not None:
            kwargs["enable_summarization"] = args.enable_summarization
        if args.mode is not None:
            kwargs["mode"] = args.mode
        result = update_settings(**kwargs)

    print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    main()
