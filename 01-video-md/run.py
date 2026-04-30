#!/usr/bin/env /Users/zyongzhu/Workbase/ai-pipeline/.venv/bin/python3
"""
01-video-md Pipeline CLI
=========================
用法：
  ./run.py graph                              打印架构图
  ./run.py start "远程工作工具"                 启动 pipeline（位置参数）
  ./run.py start --topic "远程工作工具"         启动 pipeline（命名参数）
  ./run.py start --topic "远程工作工具" --thread-id my-thread
  ./run.py start --topic "AI Agent" --urls "https://...,https://..."
  ./run.py start --topic "AI Agent" --sources "bilibili,hackernews,twitter"
  ./run.py status --thread-id my-thread        查看状态
  ./run.py continue --thread-id my-thread     继续被中断的 pipeline
  ./run.py retry --thread-id my-thread        重试失败的视频（LangGraph 原生重试）
  ./run.py approve --thread-id my-thread      批准当前待审核视频（全部通过）
  ./run.py reject --thread-id my-thread       拒绝当前待审核视频（全部拒绝）
  ./run.py modify --thread-id my-thread --approved "url1,url2"  自定义批准列表
  ./run.py list                               列出所有 thread

支持的 sources: bilibili, hackernews, zhihu, twitter, twitter_builders
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from main_graph import get_app, print_graph, print_state, list_threads, _save_review, run_pipeline


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "graph":
        print_graph()
        return

    if cmd == "list":
        threads = list_threads()
        if not threads:
            print("还没有任何 pipeline 线程")
        else:
            print(f"共 {len(threads)} 个 pipeline 线程：")
            for t in threads:
                print(f"  - {t}")
        return

    # ── 通用参数解析 ───────────────────────────────────────────────────────
    thread_id     = None
    topic         = None
    initial_videos = None
    approved_videos = None   # for modify
    rejected_videos = None   # for reject/modify
    sources_list   = None    # 多信息源
    argv = sys.argv
    i = 2
    while i < len(argv):
        arg = argv[i]
        if arg == "--thread-id"    and i + 1 < len(argv):
            thread_id = argv[i + 1]; i += 2
        elif arg == "--topic"      and i + 1 < len(argv):
            topic = argv[i + 1]; i += 2
        elif arg == "--urls"        and i + 1 < len(argv):
            initial_videos = [v.strip() for v in argv[i + 1].split(",") if v.strip()]; i += 2
        elif arg == "--sources"    and i + 1 < len(argv):
            sources_list = [s.strip() for s in argv[i + 1].split(",") if s.strip()]; i += 2
        elif arg == "--approved"    and i + 1 < len(argv):
            approved_videos = [v.strip() for v in argv[i + 1].split(",") if v.strip()]; i += 2
        elif arg == "--rejected"    and i + 1 < len(argv):
            rejected_videos = [v.strip() for v in argv[i + 1].split(",") if v.strip()]; i += 2
        elif not arg.startswith("--"):
            topic = arg; i += 1
        else:
            i += 1

    if cmd not in ("start", "status", "continue", "approve", "reject", "modify", "retry"):
        print(f"未知命令: {cmd}")
        print(__doc__)
        sys.exit(1)

    if cmd in ("status", "continue", "approve", "reject", "modify", "retry") and not thread_id:
        print(f"❌ {cmd} 需要 --thread-id")
        sys.exit(1)

    if cmd == "start" and not topic:
        print("❌ start 需要主题参数")
        print("  ./run.py start \"AI Agent 发展趋势\"")
        print("  ./run.py start --topic \"AI Agent 发展趋势\"")
        sys.exit(1)

    app   = get_app()
    config = {"configurable": {"thread_id": thread_id or "default"}}

    # ── approve ─────────────────────────────────────────────────────────────────
    if cmd == "approve":
        # 从 checkpointer 恢复 pending_videos 列表
        current_state = app.get_state(config)
        pending_videos = current_state.values.get("pending_videos", []) if current_state and current_state.values else []
        status, db_approved, db_rejected = _get_review_data(thread_id)
        if status not in ("pending",):
            print(f"⚠️  当前审核状态为 '{status}'，无需处理")
            sys.exit(0)
        # 批准：pending 时 db_approved 就是全部视频列表（已由 node_send_review_request 存入）
        to_approve = db_approved if db_approved else pending_videos
        _save_review(thread_id, "approved", approved=to_approve, rejected=db_rejected or [])
        print(f"✅ 已批准 thread '{thread_id}' 的 {len(to_approve)} 个视频，继续执行...")
        # 先用 update_state 把状态切成 approved，再 invoke 才会进 wait_review 而非重新发审核
        app.update_state(config, {
            "review_status": "approved",
            "approved_videos": to_approve,
            "rejected_videos": db_rejected or [],
            "step": "awaiting_review",
        }, as_node="wait_review")
        result = app.invoke(None, config)
        print_state(result)
        return

    # ── reject ─────────────────────────────────────────────────────────────
    if cmd == "reject":
        _save_review(thread_id, "rejected", approved=[], rejected=[])
        print(f"❌ 已拒绝 thread '{thread_id}'，Pipeline 终止")
        return

    # ── modify ──────────────────────────────────────────────────────────────────
    if cmd == "modify":
        if not approved_videos:
            print("❌ modify 需要 --approved \"url1,url2,..\"")
            sys.exit(1)
        # approve 时若未指定 approved_videos，自动用 checkpointer 中的 pending_videos
        if not approved_videos:
            current_state = app.get_state(config)
            approved_videos = current_state.values.get("pending_videos", []) if current_state and current_state.values else []
        _save_review(thread_id, "approved", approved=approved_videos, rejected=rejected_videos or [])
        print(f"✅ 已更新 thread '{thread_id}' 批准列表，继续执行...")
        result = app.invoke(None, config)
        print_state(result)
        return

    # ── status ─────────────────────────────────────────────────────────────
    if cmd == "status":
        state = app.get_state(config)
        if not state or not state.values.get("topic"):
            print(f"❌ Thread '{thread_id}' 不存在")
            threads = list_threads()
            if threads:
                print("已有线程：", ", ".join(threads))
            sys.exit(1)
        print_state(state.values)
        return

    # ── continue ──────────────────────────────────────────────────────────
    if cmd == "continue":
        print(f"▶️  继续 thread '{thread_id}'...")
        try:
            result = app.invoke(None, config)
            print_state(result)
        except Exception as e:
            # 可能是Interrupt正常中断，不算错误
            print(f"[run] invoke 返回: {e}")
            state = app.get_state(config)
            if state and state.values.get("topic"):
                print_state(state.values)
        return

    # ── retry ─────────────────────────────────────────────────────────────
    if cmd == "retry":
        state = app.get_state(config)
        if not state or not state.values.get("topic"):
            print(f"❌ Thread '{thread_id}' 不存在")
            sys.exit(1)

        failed = state.values.get("failed_videos", [])
        # 去重（累加 reducer 可能重复）
        failed = list(dict.fromkeys(failed))
        if not failed:
            print("✅ 没有失败的视频，无需重试")
            print_state(state.values)
            return

        # 从 _dispatched 列表推算每个 URL 首次出现的 idx（原始任务目录）
        dispatched = state.values.get("_dispatched", [])
        url_to_idx = {}
        for i, url in enumerate(dispatched):
            if url not in url_to_idx:   # 只取首次出现的 idx
                url_to_idx[url] = i

        # 只重试真正失败（且有原始 idx）的视频
        retry_items = [
            {"url": url, "original_idx": url_to_idx.get(url, i)}
            for i, url in enumerate(failed)
        ]

        print(f"♻️  重试 {len(retry_items)} 个失败视频（复用原始 task 目录）")
        for item in retry_items:
            print(f"  - task-{item['original_idx']} {item['url'][:60]}")

        app.update_state(config, {
            "_retry_queue": [item["url"] for item in retry_items],
            "_retry_idx_map": {item["url"]: item["original_idx"] for item in retry_items},
            "step": "transcribing",
        }, as_node="dispatcher")

        result = app.invoke(None, config)
        print_state(result)
        return

    # ── start ─────────────────────────────────────────────────────────────
    existing = app.get_state(config)
    if existing and existing.values.get("topic"):
        print(f"⚠️  Thread '{thread_id or 'default'}' 已存在，先查看状态：")
        print_state(existing.values)
        resp = input("是否继续执行? (y/n): ")
        if resp.lower() == "y":
            result = app.invoke(None, config)
            print_state(result)
        return

    print(f"\n🚀 启动 Pipeline: {topic}")
    print(f"   thread_id: {thread_id or 'default'}")
    print(f"   模式: {'--urls 注入' if initial_videos else 'LLM 推荐 + AI 过滤'}")
    if sources_list:
        print(f"   来源: {sources_list}")
    print()

    result = run_pipeline(topic, thread_id or "default", initial_videos, sources=sources_list)
    print_state(result)


def _get_review_data(thread_id):
    from main_graph import _get_review
    return _get_review(thread_id)


if __name__ == "__main__":
    main()
