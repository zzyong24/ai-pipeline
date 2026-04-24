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
  ./run.py status --thread-id my-thread        查看状态
  ./run.py continue --thread-id my-thread     继续被中断的 pipeline
  ./run.py approve --thread-id my-thread      批准当前待审核视频（全部通过）
  ./run.py reject --thread-id my-thread       拒绝当前待审核视频（全部拒绝）
  ./run.py modify --thread-id my-thread --approved "url1,url2"  自定义批准列表
  ./run.py list                               列出所有 thread
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from pipeline import get_app, print_graph, print_state, list_threads, _save_review


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
        elif arg == "--approved"    and i + 1 < len(argv):
            approved_videos = [v.strip() for v in argv[i + 1].split(",") if v.strip()]; i += 2
        elif arg == "--rejected"    and i + 1 < len(argv):
            rejected_videos = [v.strip() for v in argv[i + 1].split(",") if v.strip()]; i += 2
        elif not arg.startswith("--"):
            topic = arg; i += 1
        else:
            i += 1

    if cmd not in ("start", "status", "continue", "approve", "reject", "modify"):
        print(f"未知命令: {cmd}")
        print(__doc__)
        sys.exit(1)

    if cmd in ("status", "continue", "approve", "reject", "modify") and not thread_id:
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
    print(f"   模式: {'--urls 注入' if initial_videos else 'LLM 推荐 + 人工审核'}")
    print()

    from pipeline import PipelineState
    initial: PipelineState = {
        "topic":            topic,
        "research_results":  None,
        "pending_videos":    initial_videos or [],
        "completed_videos":  [],
        "failed_videos":     [],
        "summaries":         [],
        "_dispatched":       [],
        "book_draft":        None,
        "output_files":      None,
        "step":              "idle",
        "error":             None,
        "review_status":     "pending",
        "approved_videos":   [],
        "rejected_videos":  [],
        "thread_id":         thread_id or "default",
    }

    result = app.invoke(initial, config)
    print_state(result)


def _get_review_data(thread_id):
    from pipeline import _get_review
    return _get_review(thread_id)


if __name__ == "__main__":
    main()
