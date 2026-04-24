#!/usr/bin/env python3
"""CLI: llm-connection-test"""
import argparse
import sys
import json
from llm_connection_tester import test_connection

def main():
    parser = argparse.ArgumentParser(description="测试 MiniMax LLM 连接是否可用")
    parser.add_argument("--provider", default="minimax", help="提供商（默认 minimax）")
    args = parser.parse_args()

    result = test_connection(args.provider)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["status"] == "ok" else 1)

if __name__ == "__main__":
    main()
