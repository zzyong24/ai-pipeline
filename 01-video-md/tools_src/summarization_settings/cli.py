#!/usr/bin/env python3
"""CLI: summarization-settings get | set [--enable-summarization] [--mode] ..."""
import argparse
import sys
import json
from summarization_settings import get_settings, update_settings


def main():
    parser = argparse.ArgumentParser(description="获取/修改 msg-collect 总结配置")
    sub = parser.add_subparsers(dest="action", required=True)

    get = sub.add_parser("get", help="获取当前配置")
    set_cmd = sub.add_parser("set", help="修改配置")

    set_cmd.add_argument("--mode", choices=["standard", "agent", "auto"])
    set_cmd.add_argument("--enable-summarization", type=lambda x: x.lower() == "true",
                         metavar="true|false", help="启用/禁用自动总结")
    set_cmd.add_argument("--chunk-target-duration-sec", type=int)
    set_cmd.add_argument("--llm-call-retry-max", type=int)
    set_cmd.add_argument("--fallback-to-standard", type=lambda x: x.lower() == "true",
                         metavar="true|false",
                         help="Agent 失败时回退到 standard 模式")

    args = parser.parse_args()

    try:
        if args.action == "get":
            result = get_settings()
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            kwargs = {}
            if args.mode is not None:
                kwargs["mode"] = args.mode
            if args.enable_summarization is not None:
                kwargs["enable_summarization"] = args.enable_summarization
            if args.chunk_target_duration_sec is not None:
                kwargs["chunk_target_duration_sec"] = args.chunk_target_duration_sec
            if args.llm_call_retry_max is not None:
                kwargs["llm_call_retry_max"] = args.llm_call_retry_max
            if args.fallback_to_standard is not None:
                kwargs["fallback_to_standard_on_agent_error"] = args.fallback_to_standard
            result = update_settings(**kwargs)
            print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"❌ 错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
