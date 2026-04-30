"""
01-video-md 主 Graph — 只做编排
================================

职责：
  - 编排三个 SubGraph：research / transcribe / write_book
  - Pipeline 特有的 HITL 审核（send_review_request / wait_review）
  - fan-out 分发到 transcribe_subgraph
  - 最终通知用户

业务逻辑全部在 `subgraphs/` 下，本文件只做"编排胶水"。

规范：vault/space/crafted/study/langgraph-subgraph/subgraph-design-spec.md
"""
from __future__ import annotations

import os
import sys
import json
from pathlib import Path
from typing import TypedDict, Annotated, Dict, Any, Union, Literal, Optional, List

# ── 路径设置：把 ai-pipeline/ 加到 sys.path 以便 import subgraphs ──────────────
PIPELINE_DIR = Path(__file__).parent.resolve()         # 01-video-md/
AI_PIPELINE_ROOT = PIPELINE_DIR.parent                  # ai-pipeline/
TOOLS_SRC = PIPELINE_DIR / "tools_src"
PIPELINE_VENV = PIPELINE_DIR / ".venv" / "lib" / "python3.9" / "site-packages"

# 清理 sys.path（防止父 shell 残留）
exclude_prefixes = (
    "/Users/zyongzhu/Workbase/Msg-collect",
    "/Users/zyongzhu/.cache/uv",
)
sys.path = [p for p in sys.path if not any(p.startswith(ep) for ep in exclude_prefixes)]
sys.path.insert(0, str(PIPELINE_VENV))
sys.path.insert(0, str(TOOLS_SRC))
sys.path.insert(0, str(AI_PIPELINE_ROOT))   # 让 from subgraphs import ... 能工作

# 加载 .env
from dotenv import load_dotenv
load_dotenv(str(PIPELINE_DIR / ".env"))

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Send
from langgraph.errors import NodeInterrupt

# SubGraph
from subgraphs.research_subgraph import build_research_subgraph, ResearchState
from subgraphs.research_subgraph.config import ResearchConfig
from subgraphs.transcribe_subgraph import build_transcribe_subgraph, TranscribeState
from subgraphs.transcribe_subgraph.config import TranscribeConfig
from subgraphs.write_book_subgraph import build_write_book_subgraph, WriteBookState
from subgraphs.write_book_subgraph.config import WriteBookConfig
from subgraphs.routing_subgraph import build_routing_subgraph, RoutingState
from subgraphs.routing_subgraph.config import RoutingConfig, RoutingRule
from subgraphs.filter_subgraph import build_filter_subgraph, FilterState, FilterConfig
from subgraphs.text_extract_subgraph import build_text_extract_subgraph, TextExtractState, TextExtractConfig


# ═════════════════════════════════════════════════════════════════════════════
# 路径常量
# ═════════════════════════════════════════════════════════════════════════════
OUTPUT_BASE       = PIPELINE_DIR / "output"
CHECKPOINT_DB     = PIPELINE_DIR / "checkpoints.db"
REVIEW_DB         = PIPELINE_DIR / "review_status.db"
OUTPUT_RESEARCH   = OUTPUT_BASE / "research"
OUTPUT_TRANSCRIBE = OUTPUT_BASE / "transcribe"
OUTPUT_BOOK       = OUTPUT_BASE / "book"

for d in [OUTPUT_RESEARCH, OUTPUT_TRANSCRIBE, OUTPUT_BOOK]:
    d.mkdir(parents=True, exist_ok=True)


# ═════════════════════════════════════════════════════════════════════════════
# 主 State
# ═════════════════════════════════════════════════════════════════════════════
class PipelineState(TypedDict, total=False):
    # ───────────── ① Pipeline 输入 ─────────────
    topic: str
    thread_id: str

    # ───────────── ② 流程状态 ─────────────
    step: Literal[
        "idle", "researching", "awaiting_review",
        "transcribing", "integrating", "done", "error"
    ]
    review_status: Literal["pending", "approved", "rejected", "timeout", "none"]

    # ───────────── ③ research 产出 ─────────────
    research_results: Optional[Dict[str, Any]]
    pending_videos: Annotated[List[str], lambda a, b: a + b]

    # ───────────── ④ 审核中间状态 ─────────────
    approved_videos: Annotated[List[str], lambda a, b: a + b]
    rejected_videos: Annotated[List[str], lambda a, b: a + b]

    # ───────────── ⑤ transcribe 产出（fan-out 合并） ─────────────
    _dispatched: Annotated[List[str], lambda a, b: a + b]
    completed_videos: Annotated[List[Dict[str, Any]], lambda a, b: a + b]
    failed_videos: Annotated[List[str], lambda a, b: a + b]
    summaries: Annotated[List[Dict[str, Any]], lambda a, b: a + b]

    # ───────────── ⑤-b 重试队列 ─────────────
    # 用 lambda 取最后一个值，允许 fan-out 时多个 None 并发写入
    _retry_queue: Annotated[Optional[List[str]], lambda a, b: b]
    _retry_idx_map: Annotated[Optional[Dict[str, int]], lambda a, b: b]  # url → 原始 idx

    # ───────────── ⑥ write_book 产出 ─────────────
    book_draft: Optional[str]
    output_files: Optional[Dict[str, str]]

    # ───────────── ⑦ routing + vault 产出 ─────────────
    route_decision: Optional[Dict[str, Any]]  # routing_subgraph 输出
    vault_saved: bool                          # 是否已落库

    # ───────────── ⑧ 透传 ─────────────
    _trace_span: Optional[Any]                 # Langfuse trace（预留接口）

    # ───────────── ⑨ 多源支持 ─────────────
    sources: Optional[List[str]]               # 配置的来源列表，如 ["bilibili","hackernews"]
    source_items: Annotated[List[Dict], lambda a, b: a + b]  # research 产出的统一条目
    approved_items: Annotated[List[Dict], lambda a, b: b if b is not None else a]  # filter 通过的条目
    text_summaries: Annotated[List[Dict], lambda a, b: a + b]  # text_extract 产出
    filter_log: Optional[List[Dict]]           # filter 日志

    # ───────────── ⑩ 错误 ─────────────
    error: Optional[str]


# ═════════════════════════════════════════════════════════════════════════════
# Checkpointer
# ═════════════════════════════════════════════════════════════════════════════
_checkpointer_saver = None


def _get_checkpointer():
    global _checkpointer_saver
    if _checkpointer_saver is None:
        import sqlite3
        conn = sqlite3.connect(str(CHECKPOINT_DB), check_same_thread=False)
        _checkpointer_saver = SqliteSaver(conn)
        _checkpointer_saver.setup()
    return _checkpointer_saver


# ═════════════════════════════════════════════════════════════════════════════
# 审核 DB（Pipeline 特有的 HITL 状态）
# ═════════════════════════════════════════════════════════════════════════════
def _init_review_db():
    import sqlite3
    conn = sqlite3.connect(str(REVIEW_DB), check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS review_status (
            thread_id   TEXT PRIMARY KEY,
            status      TEXT NOT NULL DEFAULT 'pending',
            updated_at  REAL NOT NULL,
            approved_videos TEXT,
            rejected_videos TEXT
        )
    """)
    conn.commit()
    conn.close()


def _save_review(thread_id: str, status: str,
                 approved: Optional[list] = None,
                 rejected: Optional[list] = None):
    import sqlite3
    import time
    _init_review_db()
    conn = sqlite3.connect(str(REVIEW_DB), check_same_thread=False)
    conn.execute(
        "INSERT OR REPLACE INTO review_status (thread_id, status, updated_at, approved_videos, rejected_videos) VALUES (?, ?, ?, ?, ?)",
        (thread_id, status, time.time(),
         json.dumps(approved or [], ensure_ascii=False),
         json.dumps(rejected or [], ensure_ascii=False))
    )
    conn.commit()
    conn.close()


def _get_review(thread_id: str) -> tuple:
    import sqlite3
    _init_review_db()
    conn = sqlite3.connect(str(REVIEW_DB), check_same_thread=False)
    row = conn.execute(
        "SELECT status, approved_videos, rejected_videos FROM review_status WHERE thread_id=?",
        (thread_id,)
    ).fetchone()
    conn.close()
    if row:
        return row[0], json.loads(row[1] or "[]"), json.loads(row[2] or "[]")
    return "pending", [], []


# ═════════════════════════════════════════════════════════════════════════════
# 飞书通知（Pipeline 特有的外部触达）
# ═════════════════════════════════════════════════════════════════════════════
def _feishu_notify(text: str, thread_id: str) -> bool:
    """发飞书文本消息到 DM 频道。"""
    feishu_token = os.environ.get("FEISHU_APP_SECRET", "")
    app_id = os.environ.get("FEISHU_APP_ID", "cli_a957b23b43b89bdf")

    if not feishu_token:
        try:
            import subprocess
            result = subprocess.run(
                ["security", "find-generic-password", "-s", "feishu", "-w"],
                capture_output=True, text=True, timeout=5
            )
            feishu_token = result.stdout.strip()
        except Exception:
            pass

    try:
        import requests
        token_resp = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": feishu_token},
            timeout=10,
        )
        token_resp.raise_for_status()
        token = token_resp.json().get("tenant_access_token", "")
        if not token:
            return False

        payload = {
            "receive_id": "oc_dd99d0b9523e7c8ae5d9883222fdc2cb",
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }
        resp = requests.post(
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload, timeout=15,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[Feishu] 发送失败: {e}")
        return False


# ═════════════════════════════════════════════════════════════════════════════
# 编排节点 1: research 胶水层
#   - 调 research_subgraph
#   - 处理 --urls 跳过分支
#   - 把 SubGraph 的 video_urls 映射回主 State 的 pending_videos
# ═════════════════════════════════════════════════════════════════════════════
_research_subgraph = None


def _get_research_subgraph():
    global _research_subgraph
    if _research_subgraph is None:
        _research_subgraph = build_research_subgraph(
            ResearchConfig(
                timeout=30,
                output_dir=OUTPUT_RESEARCH,
                max_videos=8,
                min_score=100,   # 过滤掉播放量过低的视频
            )
        )
    return _research_subgraph


def node_research(state: PipelineState) -> Dict[str, Any]:
    # --urls 注入时跳过 research
    if state.get("pending_videos") and not state.get("research_results"):
        urls = state["pending_videos"]
        print(f"[main:research] 跳过（已有 {len(urls)} 个视频由 --urls 注入）")
        # 构建 source_items 以便 filter 使用
        source_items = [
            {"source_type": "bilibili", "title": url, "url": url, "author": "", "text_content": "", "score": 0}
            for url in urls
        ]
        return {
            "step": "transcribing",
            "review_status": "none",
            "_dispatched": [],
            "source_items": source_items,
        }

    topic = state.get("topic", "").strip()
    if not topic:
        return {"step": "error", "error": "topic 为空"}

    # 调 SubGraph（模式 2：独立 Schema）
    sub_input: ResearchState = {
        "topic": topic,
        "sources": state.get("sources") or ["bilibili"],
        "_trace_span": state.get("_trace_span"),
    }
    sub_result = _get_research_subgraph().invoke(sub_input)

    if sub_result.get("error"):
        return {"step": "error", "error": sub_result["error"]}

    urls = sub_result.get("video_urls", [])
    selected = sub_result.get("selected_videos", [])
    print(f"[main:research] SubGraph 返回 {len(urls)} 个视频")

    return {
        "research_results": {"topic": topic, "selected_videos": selected},
        "pending_videos": urls,
        "source_items": sub_result.get("source_items", []),
        "sources": state.get("sources"),
        "step": "awaiting_review",
        "review_status": "pending",
        "_dispatched": [],
        "approved_videos": [],
        "rejected_videos": [],
    }


# ═════════════════════════════════════════════════════════════════════════════
# 编排节点 1.5: filter 胶水层（AI 相关性过滤，替代 HITL）
# ═════════════════════════════════════════════════════════════════════════════
_filter_subgraph = None


def _get_filter_subgraph():
    global _filter_subgraph
    if _filter_subgraph is None:
        _filter_subgraph = build_filter_subgraph(FilterConfig(timeout=90))
    return _filter_subgraph


def node_filter(state: PipelineState) -> Dict[str, Any]:
    """AI 相关性过滤节点，替代 HITL。"""
    topic = state.get("topic", "")
    source_items = state.get("source_items", [])
    # 向后兼容：source_items 为空时，把 pending_videos 转为 bilibili 条目
    if not source_items:
        video_urls = state.get("pending_videos") or []
        source_items = [
            {"source_type": "bilibili", "title": url, "url": url, "author": "", "text_content": "", "score": 0}
            for url in video_urls
        ]

    print(f"[main:filter] 开始 AI 过滤，{len(source_items)} 个候选...")
    sub_input = {"topic": topic, "candidates": source_items, "_trace_span": state.get("_trace_span")}
    try:
        sub_result = _get_filter_subgraph().invoke(sub_input)
        approved = sub_result.get("approved_items", source_items)  # 失败时兜底保留全部
        rejected = sub_result.get("rejected_items", [])
        filter_log = sub_result.get("filter_log", [])
        print(f"[main:filter] 完成：通过 {len(approved)} / {len(source_items)}")
        return {
            "approved_items": approved,
            "pending_videos": [i["url"] for i in approved if i.get("source_type") == "bilibili"],
            "filter_log": filter_log,
            "step": "transcribing",
        }
    except Exception as e:
        print(f"[main:filter] 失败，兜底保留所有: {e}")
        return {
            "approved_items": source_items,
            "pending_videos": [i["url"] for i in source_items if i.get("source_type") == "bilibili"],
            "step": "transcribing",
        }


# ═════════════════════════════════════════════════════════════════════════════
# 编排节点 2: send_review_request (HITL - Pipeline 特有)
# ═════════════════════════════════════════════════════════════════════════════
def node_send_review_request(state: PipelineState) -> Dict[str, Any]:
    """发审核请求 → 触发 Interrupt 等待用户响应。"""
    thread_id = state.get("thread_id", "default")
    videos = state.get("pending_videos", [])
    review_st = state.get("review_status", "pending")

    # --urls 模式：跳过审核
    if review_st == "none":
        print("[main:send_review] --urls 模式，跳过审核")
        return {"step": "transcribing", "_dispatched": []}

    lines = [f"🎬 **视频审核请求**（主题：{state['topic']}）", ""]
    for i, url in enumerate(videos, 1):
        lines.append(f"{i}. {url}")
    lines.append("")
    lines.append("回复 `approve` 全部通过，或 `reject` 全部拒绝，或 `modify: 去掉某几个` 修改")
    text = "\n".join(lines)

    _feishu_notify(text, thread_id)
    _save_review(thread_id, "pending", approved=videos, rejected=[])
    print(f"[main:send_review] 已发送审核请求，等待用户...")

    raise NodeInterrupt(
        f"等待人工审核视频列表（1小时后自动拒绝）：\n{text}",
        id="video-review",
    )


# ═════════════════════════════════════════════════════════════════════════════
# 编排节点 3: wait_review (Interrupt 恢复后进入)
# ═════════════════════════════════════════════════════════════════════════════
def node_wait_review(state: PipelineState) -> Dict[str, Any]:
    thread_id = state.get("thread_id", "default")
    status, approved, rejected = _get_review(thread_id)

    print(f"[main:wait_review] 审核结果: {status}")

    if status == "pending":
        status = "timeout"
        _save_review(thread_id, "timeout")
        print("[main:wait_review] 超时，自动拒绝")

    if status in ("rejected", "timeout"):
        print("[main:wait_review] 用户拒绝/超时，Pipeline 终止")
        return {
            "step": "done",
            "pending_videos": [],
            "review_status": status,
            "approved_videos": [],
            "rejected_videos": state.get("pending_videos", []),
        }

    final_videos = approved if approved else state.get("pending_videos", [])
    print(f"[main:wait_review] 审核通过，{len(final_videos)}/{len(state.get('pending_videos', []))} 进入转录")

    return {
        "step": "transcribing",
        "review_status": status,
        "pending_videos": final_videos,
        "approved_videos": approved,
        "rejected_videos": rejected,
        "_dispatched": [],
    }


# ═════════════════════════════════════════════════════════════════════════════
# 编排节点 4: dispatcher + route_dispatcher
#   - 主 Graph 纯分发逻辑
#   - fan-out 通过 Send 调 transcribe_subgraph
# ═════════════════════════════════════════════════════════════════════════════
def node_dispatcher(state: PipelineState) -> Dict[str, Any]:
    """纯分发 node：只记录，不更新 state。"""
    dispatched = set(state.get("_dispatched", []))
    pending = [v for v in state.get("pending_videos", []) if v not in dispatched]
    if pending:
        print(
            f"[main:dispatcher] 待分发: {len(pending)} 个视频 "
            f"（累计完成 {len(state.get('completed_videos', []))}/{len(state.get('pending_videos', []))}）"
        )
    return {}


def route_dispatcher(state: PipelineState):
    """List[Send] 只能从 conditional edge 返回。

    优先级：
    1. _retry_queue（由 retry 命令注入，重试失败视频）
    2. approved_items 中未分发的（多源分流）
    3. pending_videos 中未分发的（向后兼容）
    4. 两者都空 → write_book_node

    并发控制：每批最多 cpu_count // 2 个（8核→4），避免 Whisper 超时。
    """
    import os
    import multiprocessing
    cpu = multiprocessing.cpu_count()
    batch_size = max(1, min(cpu // 2, 4))

    # 优先消费重试队列
    retry_queue = state.get("_retry_queue") or []
    if retry_queue:
        retry_idx_map = state.get("_retry_idx_map") or {}
        batch = retry_queue[:batch_size]
        remaining = len(retry_queue) - len(batch)
        print(f"[main:route] ♻️  重试队列：本批 {len(batch)} 个（剩余 {remaining} 个）")
        return [
            Send(
                "transcribe_single",
                {
                    "video": video,
                    # 用原始 idx，确保指向已有 srt 的目录
                    "idx": retry_idx_map.get(video, len(state.get("_dispatched", [])) + i),
                    "topic": state.get("topic", ""),
                    "_trace_span": state.get("_trace_span"),
                    "_is_retry": True,
                },
            )
            for i, video in enumerate(batch)
        ]

    # 多源分流：从 approved_items 分发
    approved_items = state.get("approved_items", [])
    dispatched = set(state.get("_dispatched", []))

    if approved_items:
        # 过滤掉已分发的
        undispatched_items = [item for item in approved_items if item.get("url", "") not in dispatched]

        if undispatched_items:
            batch_items = undispatched_items[:batch_size]
            remaining = len(undispatched_items) - len(batch_items)
            print(f"[main:route] 本批分发 {len(batch_items)} 个（剩余 {remaining} 个待下批），"
                  f"并发数={batch_size}（{cpu} 核 // 2）")

            sends = []
            for i, item in enumerate(batch_items):
                src_type = item.get("source_type", "bilibili")
                url = item.get("url", "")
                idx = len(dispatched) + i

                if src_type == "bilibili":
                    sends.append(Send(
                        "transcribe_single",
                        {
                            "video": url,
                            "idx": idx,
                            "topic": state.get("topic", ""),
                            "_trace_span": state.get("_trace_span"),
                        },
                    ))
                else:
                    sends.append(Send(
                        "text_extract_single",
                        {
                            "source_type": src_type,
                            "source_url": url,
                            "title": item.get("title", ""),
                            "text_content": item.get("text_content", ""),
                            "author": item.get("author", ""),
                            "idx": idx,
                            "topic": state.get("topic", ""),
                            "_trace_span": state.get("_trace_span"),
                        },
                    ))

            return sends if sends else "write_book_node"

    # 向后兼容：pending_videos 中未分发的
    pending = [v for v in state.get("pending_videos", []) if v not in dispatched]

    if not pending:
        print("[main:route] 无待处理内容，进入 write_book")
        return "write_book_node"

    batch = pending[:batch_size]
    remaining = len(pending) - len(batch)
    print(f"[main:route] 本批分发 {len(batch)} 个（剩余 {remaining} 个待下批），"
          f"并发数={batch_size}（{cpu} 核 // 2）")

    return [
        Send(
            "transcribe_single",
            {
                "video": video,
                "idx": len(dispatched) + i,
                "topic": state.get("topic", ""),
                "_trace_span": state.get("_trace_span"),
            },
        )
        for i, video in enumerate(batch)
    ]


# ═════════════════════════════════════════════════════════════════════════════
# 编排节点 5: transcribe_single_wrapper
#   - 调 transcribe_subgraph
#   - 映射父子 State
# ═════════════════════════════════════════════════════════════════════════════
_transcribe_subgraph = None


def _get_transcribe_subgraph():
    global _transcribe_subgraph
    if _transcribe_subgraph is None:
        _transcribe_subgraph = build_transcribe_subgraph(
            TranscribeConfig(
                timeout_download=300,
                timeout_transcribe=600,   # 字幕优先后只有无字幕视频走 Whisper，给足时间
                timeout_summarize=120,
                output_base=OUTPUT_TRANSCRIBE,
                tools_src=TOOLS_SRC,
                use_subtitle_first=True,
            )
        )
    return _transcribe_subgraph


def node_transcribe_single(sub_state: Dict[str, Any]) -> Dict[str, Any]:
    """父子 State 映射层 + 调用 transcribe_subgraph。

    父传入的是 Send 的 payload: {"video": url, "idx": N, "topic": str}
    返回主 State 需要的：completed_videos / summaries / failed_videos / _dispatched
    重试时还返回 _retry_queue（移除已处理项）
    """
    video = sub_state["video"]
    idx = sub_state.get("idx", 0)
    topic = sub_state.get("topic", "")
    is_retry = sub_state.get("_is_retry", False)

    # 父 → 子 State 映射
    sub_input: TranscribeState = {
        "video_url": video,
        "task_idx": idx,
        "topic": topic,
        "_trace_span": sub_state.get("_trace_span"),
    }

    try:
        sub_result = _get_transcribe_subgraph().invoke(sub_input)
    except Exception as e:
        print(f"[main:transcribe:{idx}] SubGraph 调用异常: {e}")
        result = {
            "completed_videos": [],
            "failed_videos": [video],
            "_dispatched": [video],
        }
        if is_retry:
            result["_retry_queue"] = None   # 清空重试队列（由 dispatcher 驱动下批）
        return result

    # 子 → 父 State 映射
    if not sub_result.get("success"):
        print(f"[main:transcribe:{idx}] 失败: {sub_result.get('error')}")
        result = {
            "completed_videos": [],
            "failed_videos": [video],
            "_dispatched": [video],
        }
        if is_retry:
            result["_retry_queue"] = None
        return result

    summary_text = sub_result.get("summary", "")
    title = sub_result.get("title") or video

    result = {
        "completed_videos": [{
            "url": video,
            "title": title,
            "file_path": sub_result.get("file_path", ""),
            "srt_path": sub_result.get("srt_path", ""),
            "summary": summary_text,
            "duration": sub_result.get("duration", 0),
        }],
        "summaries": [{
            "video": video,
            "title": title,
            "summary": summary_text,
        }],
        "failed_videos": [],
        "_dispatched": [video],
    }
    if is_retry:
        result["_retry_queue"] = None
    return result


# ═════════════════════════════════════════════════════════════════════════════
# 编排节点 5.5: text_extract_single_wrapper
#   - 调 text_extract_subgraph
#   - 映射父子 State（非视频文本内容）
# ═════════════════════════════════════════════════════════════════════════════
_text_extract_subgraph = None


def _get_text_extract_subgraph():
    global _text_extract_subgraph
    if _text_extract_subgraph is None:
        _text_extract_subgraph = build_text_extract_subgraph(TextExtractConfig(timeout=90))
    return _text_extract_subgraph


def node_text_extract_single(sub_state: Dict[str, Any]) -> Dict[str, Any]:
    """文本内容提炼节点（twitter/hackernews/zhihu）。"""
    idx = sub_state.get("idx", 0)
    url = sub_state.get("source_url", "")
    src_type = sub_state.get("source_type", "unknown")
    print(f"[main:text_extract:{idx}] {src_type} — {url[:60]}")

    try:
        sub_result = _get_text_extract_subgraph().invoke(sub_state)
        summary_text = sub_result.get("summary")
        if summary_text:
            summary_item = {
                "video": url,
                "title": sub_state.get("title", url),
                "source_type": src_type,
                "summary": summary_text,
            }
            return {
                "summaries": [summary_item],
                "completed_videos": [{"url": url, "title": sub_state.get("title", url), "source_type": src_type, "summary": summary_text}],
                "_dispatched": [url],
            }
        else:
            print(f"[main:text_extract:{idx}] 无 summary: {sub_result.get('error')}")
            return {"failed_videos": [url], "_dispatched": [url]}
    except Exception as e:
        print(f"[main:text_extract:{idx}] 异常: {e}")
        return {"failed_videos": [url], "_dispatched": [url]}


# ═════════════════════════════════════════════════════════════════════════════
# 编排节点 6: write_book_node (调 write_book_subgraph)
# ═════════════════════════════════════════════════════════════════════════════
_write_book_subgraph = None


def _get_write_book_subgraph():
    global _write_book_subgraph
    if _write_book_subgraph is None:
        _write_book_subgraph = build_write_book_subgraph(
            WriteBookConfig(
                timeout_aggregate=180,
                timeout_write=300,
                min_chapters=5,
                min_words=2000,
            )
        )
    return _write_book_subgraph


def node_write_book(state: PipelineState) -> Dict[str, Any]:
    """调 write_book_subgraph 生成书稿。"""
    topic = state.get("topic", "")
    summaries = state.get("summaries", [])

    print(f"[main:write_book] 调 SubGraph，{len(summaries)} 个摘要")

    sub_input: WriteBookState = {
        "topic": topic,
        "summaries": summaries,
        "_trace_span": state.get("_trace_span"),
    }

    try:
        sub_result = _get_write_book_subgraph().invoke(sub_input)
    except Exception as e:
        print(f"[main:write_book] SubGraph 异常: {e}")
        return {"step": "error", "error": f"write_book failed: {e}"}

    book = sub_result.get("book") or ""
    return {
        "book_draft": book,
        "step": "integrating",
    }


# ═════════════════════════════════════════════════════════════════════════════
# 编排节点 7: route_content (调 routing_subgraph)
# ═════════════════════════════════════════════════════════════════════════════
_routing_subgraph = None


def _get_routing_subgraph():
    """单例：构建 routing_subgraph。

    规则集为 video-md Pipeline 定制，覆盖常见的视频/播客/论文/教程/代码来源。
    """
    global _routing_subgraph
    if _routing_subgraph is None:
        _routing_subgraph = build_routing_subgraph(RoutingConfig(rules=[
            RoutingRule(source_type="video",   content_type="study_doc",      topic="reading"),
            RoutingRule(source_type="podcast", content_type="study_doc",      topic="reading"),
            RoutingRule(keywords=["论文", "研究", "实验", "数据集"],
                        content_type="knowledge_card", topic="ai"),
            RoutingRule(keywords=["教程", "手册", "实战", "指南"],
                        content_type="study_doc",      topic="reading"),
            RoutingRule(domain="github.com",   content_type="note",           topic="dev"),
        ]))
    return _routing_subgraph


def node_route_content(state: PipelineState) -> Dict[str, Any]:
    """调 routing_subgraph，把 RouteDecision 写回主 State。"""
    sub_input: RoutingState = {
        "title": state.get("topic", ""),
        "summary": (state.get("book_draft") or "")[:500],
        "source_type": "video",
        "source_url": (state.get("approved_videos") or [""])[0],
        "_trace_span": state.get("_trace_span"),
    }
    sub_result = _get_routing_subgraph().invoke(sub_input)
    decision = sub_result.get("route_decision")
    method = sub_result.get("match_method", "rule")
    print(f"[main:route_content] -> {decision} (method={method})")
    return {"route_decision": decision}


# ═════════════════════════════════════════════════════════════════════════════
# 编排节点 8: save_to_vault (根据路由决策落库)
# ═════════════════════════════════════════════════════════════════════════════
def node_save_to_vault(state: PipelineState) -> Dict[str, Any]:
    """根据 RouteDecision 生成规范 frontmatter，写入 vault 目录。

    TODO: 当前直接写文件，后续替换为 ThirdSpace MCP 调用。
    """
    import datetime

    decision = state.get("route_decision")
    book = state.get("book_draft") or ""
    topic_name = state.get("topic", "")

    if not decision:
        print("[main:save_to_vault] 无路由决策，跳过落库")
        return {"vault_saved": False}

    content_type = decision.get("content_type", "study_doc")
    topic = decision.get("topic", "reading")
    tags = decision.get("tags", [])
    today = datetime.date.today().isoformat()

    frontmatter = f"""---
title: {topic_name}
date: {today}
type: {content_type}
topic: {topic}
tags: {tags}
status: draft
source: ai-pipeline/01-video-md
---

"""

    # 写到本地 output/vault/ 目录（与 ThirdSpace 打通前的临时目录）
    safe_topic = "".join(c if c.isalnum() or c in " -_" else "_" for c in topic_name)[:20]
    vault_out = OUTPUT_BASE / "vault" / topic / f"{today}_{safe_topic}.md"
    vault_out.parent.mkdir(parents=True, exist_ok=True)
    vault_out.write_text(frontmatter + book, encoding="utf-8")
    print(f"[main:save_to_vault] 已写入: {vault_out}")

    return {"vault_saved": True}


# ═════════════════════════════════════════════════════════════════════════════
# 编排节点 9: notify (Pipeline 特有的输出+通知)
def _generate_source_viz(topic: str, summaries: list, completed_videos: list, output_dir: Path) -> str:
    """生成来源占比可视化 HTML，返回文件路径。"""
    import datetime

    # 统计每个来源的字数占比（用 summary 长度作为内容贡献度代理指标）
    sources = []
    total_chars = 0
    for s in summaries:
        chars = len(s.get("summary", ""))
        total_chars += chars
        # 尝试从 completed_videos 匹配更多元数据
        url = s.get("video", "")
        title = s.get("title", url[:40])
        sources.append({"url": url, "title": title, "chars": chars})

    if total_chars == 0:
        return ""

    # 构建 HTML
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    safe_topic = "".join(c if c.isalnum() or c in " -_" else "_" for c in topic)[:20]
    html_path = output_dir / f"{safe_topic}_来源分析.html"

    bar_items = ""
    table_rows = ""
    colors = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3",
              "#937860", "#DA8BC3", "#8C8C8C", "#CCB974", "#64B5CD"]

    for i, src in enumerate(sources):
        pct = round(src["chars"] / total_chars * 100, 1)
        color = colors[i % len(colors)]
        short_title = src["title"][:45] + ("…" if len(src["title"]) > 45 else "")
        bar_items += f"""
        <div class="bar-row">
          <div class="bar-label" title="{src['title']}">[{i+1}] {short_title}</div>
          <div class="bar-wrap">
            <div class="bar" style="width:{pct}%;background:{color}"></div>
            <span class="bar-pct">{pct}%</span>
          </div>
        </div>"""
        table_rows += f"""
        <tr>
          <td><span class="dot" style="background:{color}">●</span> {i+1}</td>
          <td><a href="{src['url']}" target="_blank">{short_title}</a></td>
          <td class="num">{src['chars']:,}</td>
          <td class="num">{pct}%</td>
        </tr>"""

    failed_count = len(completed_videos)  # actually completed
    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>{topic} — 来源分析</title>
<style>
  body {{ font-family: -apple-system, "PingFang SC", sans-serif; max-width: 860px; margin: 40px auto; padding: 0 20px; color: #222; }}
  h1 {{ font-size: 1.4em; border-bottom: 2px solid #4C72B0; padding-bottom: 8px; }}
  .meta {{ color: #666; font-size: 0.85em; margin-bottom: 24px; }}
  .section {{ margin: 28px 0; }}
  h2 {{ font-size: 1.1em; color: #333; margin-bottom: 12px; }}
  .bar-row {{ display: flex; align-items: center; margin: 6px 0; }}
  .bar-label {{ width: 280px; font-size: 0.82em; color: #444; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding-right: 10px; }}
  .bar-wrap {{ flex: 1; display: flex; align-items: center; }}
  .bar {{ height: 20px; border-radius: 3px; min-width: 2px; transition: width 0.3s; }}
  .bar-pct {{ margin-left: 8px; font-size: 0.82em; color: #555; width: 40px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.88em; }}
  th {{ background: #f0f0f0; padding: 8px 10px; text-align: left; border-bottom: 2px solid #ddd; }}
  td {{ padding: 7px 10px; border-bottom: 1px solid #eee; vertical-align: top; }}
  td a {{ color: #4C72B0; text-decoration: none; }}
  td a:hover {{ text-decoration: underline; }}
  .num {{ text-align: right; color: #555; }}
  .dot {{ margin-right: 4px; }}
  .stat-box {{ display: flex; gap: 20px; flex-wrap: wrap; }}
  .stat {{ background: #f8f9fa; border-radius: 6px; padding: 12px 18px; }}
  .stat .n {{ font-size: 1.8em; font-weight: bold; color: #4C72B0; }}
  .stat .l {{ font-size: 0.82em; color: #666; margin-top: 2px; }}
</style>
</head>
<body>
<h1>📊 {topic} — 来源分析报告</h1>
<div class="meta">生成时间：{now} · 共 {len(sources)} 个来源</div>

<div class="section">
  <div class="stat-box">
    <div class="stat"><div class="n">{len(sources)}</div><div class="l">来源数量</div></div>
    <div class="stat"><div class="n">{total_chars:,}</div><div class="l">总内容字符数</div></div>
    <div class="stat"><div class="n">{round(total_chars/len(sources)):,}</div><div class="l">平均每源字符数</div></div>
  </div>
</div>

<div class="section">
  <h2>内容贡献占比（以摘要字数为代理指标）</h2>
  {bar_items}
</div>

<div class="section">
  <h2>来源明细</h2>
  <table>
    <tr><th>#</th><th>来源标题</th><th class="num">字符数</th><th class="num">占比</th></tr>
    {table_rows}
  </table>
</div>

<div class="section">
  <p style="color:#888;font-size:0.8em">
    注：占比基于 LLM 摘要字数，反映各来源信息密度，不代表原始视频时长。
    点击来源标题可直接访问原始链接。
  </p>
</div>
</body>
</html>"""

    html_path.write_text(html, encoding="utf-8")
    print(f"[main:notify] 来源分析已保存: {html_path}")
    return str(html_path)


# ═════════════════════════════════════════════════════════════════════════════
# 编排节点 7: notify (Pipeline 特有的输出+通知)
# ═════════════════════════════════════════════════════════════════════════════
def node_notify(state: PipelineState) -> Dict[str, Any]:
    topic = state.get("topic", "")
    book = state.get("book_draft") or ""
    summaries = state.get("summaries", [])
    completed_videos = state.get("completed_videos", [])

    safe_topic = "".join(c if c.isalnum() or c in " -_" else "_" for c in topic)[:20]
    output_file = OUTPUT_BOOK / f"{safe_topic}.md"
    output_file.write_text(f"# {topic}\n\n{book}", encoding="utf-8")

    completed = len(completed_videos)
    failed = len(state.get("failed_videos", []))

    # 生成来源占比可视化
    viz_file = ""
    if summaries:
        viz_file = _generate_source_viz(topic, summaries, completed_videos, OUTPUT_BOOK)

    print(f"[main:notify] 参考报告已保存: {output_file}")
    print(f"[main:notify] 完成！{completed} 个来源，失败 {failed} 个")

    output_files = {"report": str(output_file)}
    if viz_file:
        output_files["source_viz"] = viz_file

    _feishu_notify(
        f"✅ Pipeline 完成！主题：{topic}\n"
        f"来源：{completed} 个 | 失败：{failed} 个\n"
        f"报告：{output_file}",
        state.get("thread_id", "default"),
    )

    return {
        "step": "done",
        "output_files": output_files,
    }


# ═════════════════════════════════════════════════════════════════════════════
# 构建主 Graph
# ═════════════════════════════════════════════════════════════════════════════
def build_graph():
    builder = StateGraph(PipelineState)

    builder.add_node("research", node_research)
    builder.add_node("filter", node_filter)
    builder.add_node("send_review_request", node_send_review_request)
    builder.add_node("wait_review", node_wait_review)
    builder.add_node("dispatcher", node_dispatcher)
    builder.add_node("transcribe_single", node_transcribe_single)
    builder.add_node("text_extract_single", node_text_extract_single)
    builder.add_node("write_book_node", node_write_book)
    builder.add_node("route_content", node_route_content)
    builder.add_node("save_to_vault", node_save_to_vault)
    builder.add_node("notify", node_notify)

    builder.add_edge(START, "research")
    builder.add_edge("research", "filter")
    builder.add_edge("filter", "dispatcher")

    # HITL 保留但不接入主流程（可由 --urls 模式或手动触发）
    # builder.add_edge("research", "send_review_request")
    # builder.add_conditional_edges(
    #     "send_review_request",
    #     lambda s: "dispatcher" if s.get("review_status") == "none" else "wait_review",
    #     {"wait_review": "wait_review", "dispatcher": "dispatcher"},
    # )
    # builder.add_edge("wait_review", "dispatcher")

    # fan-out 循环
    builder.add_edge("transcribe_single", "dispatcher")
    builder.add_edge("text_extract_single", "dispatcher")

    # dispatcher → conditional edge（返回 Send 列表或下一步名字）
    builder.add_conditional_edges(
        "dispatcher",
        route_dispatcher,
        {"write_book_node": "write_book_node"},
    )

    builder.add_edge("write_book_node", "route_content")
    builder.add_edge("route_content", "save_to_vault")
    builder.add_edge("save_to_vault", "notify")
    builder.add_edge("notify", END)

    return builder.compile(checkpointer=_get_checkpointer(), debug=False)


# ═════════════════════════════════════════════════════════════════════════════
# 单例 + 辅助函数
# ═════════════════════════════════════════════════════════════════════════════
_app = None


def get_app():
    global _app
    if _app is None:
        _app = build_graph()
    return _app


def run_pipeline(topic: str, thread_id: str, initial_videos: list = None, sources: list = None):
    """启动 Pipeline，自动接入 Langfuse 全链路 trace（v4 最佳实践）。

    接入方式：
    - @observe 装饰器（见下方 _run_pipeline_traced）创建顶层 trace
    - LangChain CallbackHandler 传入 graph.invoke()，自动 trace 所有节点和 LLM 调用
    - 未配置 Langfuse 时静默跳过，Pipeline 正常运行
    """
    from subgraphs.shared.observability import (
        get_observe_decorator, get_langfuse_callback,
        get_current_trace_id, update_current_trace, flush,
    )

    # 用 @observe 包裹核心逻辑，创建顶层 trace
    observe = get_observe_decorator(name="video-md-pipeline", as_type="span")

    @observe
    def _run():
        # 在 @observe 上下文内设置 session_id、topic 元数据
        update_current_trace(
            session_id=thread_id,
            metadata={"topic": topic},
            tags=["video-md"],
        )

        # 获取当前 trace ID，传给 CallbackHandler 以关联 LangGraph 子 trace
        trace_id = get_current_trace_id()
        handler = get_langfuse_callback(trace_id=trace_id)

        initial: PipelineState = {
            "topic": topic,
            "thread_id": thread_id,
            "sources": sources or ["bilibili"],
            "_trace_span": None,
            "research_results": None,
            "pending_videos": initial_videos or [],
            "completed_videos": [],
            "failed_videos": [],
            "summaries": [],
            "_dispatched": [],
            "source_items": [],
            "approved_items": [],
            "text_summaries": [],
            "book_draft": None,
            "output_files": None,
            "step": "idle",
            "error": None,
            "review_status": "pending",
            "approved_videos": [],
            "rejected_videos": [],
        }

        graph_config: dict = {"configurable": {"thread_id": thread_id}}
        if handler:
            graph_config["callbacks"] = [handler]

        return get_app().invoke(initial, graph_config)

    result = _run()
    flush()   # 确保所有 trace 数据上报
    return result


def list_threads():
    import sqlite3
    if not CHECKPOINT_DB.exists():
        return []
    conn = sqlite3.connect(str(CHECKPOINT_DB))
    rows = conn.execute("SELECT DISTINCT thread_id FROM checkpoints ORDER BY thread_id").fetchall()
    conn.close()
    return [r[0] for r in rows]


def print_graph():
    print("""
┌──────────────────────────────────────────────────────────────────────┐
│           01-video-md Main Graph (只做编排)                         │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  START ──▶ [research]* ──▶ [send_review_request]                   │
│                                       │                              │
│                                       ▼  Interrupt                   │
│                             （飞书通知 → Hermes 审核）               │
│                                       │                              │
│                                       ▼                              │
│                                  [wait_review]                       │
│                                       ▼                              │
│                                [dispatcher]                          │
│                                       │                              │
│                     ┌────────────────┴────────────────┐             │
│                     │ conditional edge route_dispatcher│             │
│                     └────────────────┬────────────────┘             │
│                                      │                              │
│              List[Send]              │ 无待处理                      │
│                    ▼                 ▼                              │
│       [transcribe_single]*   [write_book_node]*                     │
│          (调 transcribe_subgraph)  (调 write_book_subgraph)          │
│                    │                 │                              │
│                    └─── dispatcher ──┘                              │
│                                      ▼                              │
│                                 [notify] ──▶ END                    │
│                                                                      │
│  * 调 SubGraph：research_subgraph / transcribe_subgraph /           │
│                 write_book_subgraph                                  │
└──────────────────────────────────────────────────────────────────────┘
""")


def print_state(state: Dict[str, Any]):
    step = state.get("step", "?")
    completed = len(state.get("completed_videos", []))
    total = len(state.get("pending_videos", []))
    summaries = len(state.get("summaries", []))
    book_ready = bool(state.get("book_draft"))
    output = state.get("output_files")
    error = state.get("error")
    review = state.get("review_status", "none")
    failed = len(state.get("failed_videos", []))

    step_emoji = {
        "idle": "⏳", "researching": "🔍", "awaiting_review": "👀",
        "transcribing": "🎬", "integrating": "📖",
        "done": "✅", "error": "❌",
    }.get(step, "❓")

    print(f"\n{'='*55}")
    print(f"  当前步骤:   {step_emoji} {step}")
    print(f"  审核状态:   {review}")
    print(f"  转录进度:   {completed}/{total} 个视频（失败 {failed} 个）")
    print(f"  总结数量:   {summaries}")
    print(f"  书稿就绪:   {'✅' if book_ready else '❌'}")
    if output:
        for k, v in output.items():
            print(f"  输出文件:   {k} → {v}")
    if error:
        print(f"  错误:       {error}")
    print(f"{'='*55}\n")
