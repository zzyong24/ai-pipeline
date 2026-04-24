"""
01-video-md Pipeline — 视频主题研究 → 人工审核 → 批量转录 → AI 书稿生成
======================================================================
LangGraph v1.x / Send API / SqliteSaver Checkpointer / Interrupt 人工审核
Python: /Users/zyongzhu/Workbase/ai-pipeline/.venv/bin/python

流程：
  research → send_review_request（发飞书通知）→ [Interrupt 暂停]
            → wait_review（Hermes 唤醒，继续或终止）
            → dispatcher → [fan-out: transcribe_single × N]
            → dispatcher（循环）→ summarize_aggregator
            → write_book → notify → END

规范：
  - List[Send] 只从 conditional edge 返回，不从 node 返回
  - 每个工具调用都有独立超时，超时视为失败，不卡死
  - output 全部放在 ./output/{工具}/{任务}/ 目录下
  - review_status: pending | approved | rejected | timeout
"""

from __future__ import annotations

import os
import re
import json
import signal
import threading
from pathlib import Path
from typing import TypedDict, Annotated, Dict, Any, Union, Literal, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

# ── venv + tools setup ────────────────────────────────────────────────────────
PIPELINE_DIR = Path(__file__).parent.resolve()        # 01-video-md/
TOOLS_SRC = PIPELINE_DIR / "tools_src"
PIPELINE_VENV = PIPELINE_DIR / ".venv" / "lib" / "python3.9" / "site-packages"

# 清理 sys.path（防止父 shell 残留 Msg-collect 等路径）
import sys as _sys
exclude_prefixes = (
    "/Users/zyongzhu/Workbase/Msg-collect",
    "/Users/zyongzhu/.cache/uv",
)
_sys.path = [p for p in _sys.path if not any(p.startswith(ep) for ep in exclude_prefixes)]
# 重建：pipeline venv（优先 LangGraph 等）→ tools_src（覆盖同名模块）
_sys.path.insert(0, str(PIPELINE_VENV))
_sys.path.insert(0, str(TOOLS_SRC))
sys = _sys  # 后续代码使用 sys.path

# 加载 .env
from dotenv import load_dotenv
load_dotenv(str(PIPELINE_DIR / ".env"))

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Send, Interrupt
from langgraph.errors import NodeInterrupt

# ── 常量 ─────────────────────────────────────────────────────────────────────
# 节点超时时间（秒）
TIMEOUT_RESEARCH        = 120   # 2 分钟
TIMEOUT_DOWNLOAD        = 300   # 5 分钟
TIMEOUT_TRANSCRIBE      = 300   # 5 分钟（Whisper 本地转录）
TIMEOUT_SUMMARIZE       = 120   # 2 分钟
TIMEOUT_INTEGRATE       = 180   # 3 分钟
TIMEOUT_WRITE_BOOK      = 300   # 5 分钟

# 审核超时（秒），超时自动拒绝
REVIEW_TIMEOUT_SECONDS  = 3600  # 1 小时

# ── 路径规范 ────────────────────────────────────────────────────────────────
OUTPUT_BASE    = PIPELINE_DIR / "output"                  # ./output/
CHECKPOINT_DB  = PIPELINE_DIR / "checkpoints.db"         # ./checkpoints.db
REVIEW_DB      = PIPELINE_DIR / "review_status.db"       # 人工审核状态持久化

OUTPUT_RESEARCH   = OUTPUT_BASE / "research"
OUTPUT_TRANSCRIBE = OUTPUT_BASE / "transcribe"
OUTPUT_SUMMARIZE  = OUTPUT_BASE / "summarize"
OUTPUT_BOOK       = OUTPUT_BASE / "book"

for d in [OUTPUT_RESEARCH, OUTPUT_TRANSCRIBE, OUTPUT_SUMMARIZE, OUTPUT_BOOK]:
    d.mkdir(parents=True, exist_ok=True)


# ── Checkpointer ─────────────────────────────────────────────────────────────
_checkpointer_saver = None


def _get_checkpointer():
    global _checkpointer_saver
    if _checkpointer_saver is None:
        import sqlite3
        conn = sqlite3.connect(str(CHECKPOINT_DB), check_same_thread=False)
        _checkpointer_saver = SqliteSaver(conn)
        _checkpointer_saver.setup()
    return _checkpointer_saver


# ── 审核状态 DB（跨进程）──────────────────────────────────────────────────────
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
    import sqlite3, time
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


# ── LLM ─────────────────────────────────────────────────────────────────────
MINIMAX_KEY = os.environ.get("MINIMAX_CN_API_KEY", "")


def llm_minimax(prompt: str, model: str = "MiniMax-M2", timeout: int = 120) -> str:
    if not MINIMAX_KEY:
        raise RuntimeError("MINIMAX_CN_API_KEY 环境变量未设置")
    import requests
    resp = requests.post(
        "https://api.minimax.chat/v1/text/chatcompletion_v2",
        headers={"Authorization": f"Bearer {MINIMAX_KEY}", "Content-Type": "application/json"},
        json={"model": model, "messages": [{"role": "user", "content": prompt}]},
        timeout=timeout,
    )
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"].get("content") or ""
    return re.sub(r"\{\{[\s\S]*?\}\}", "", raw).strip()


# ── 超时装饰器 ────────────────────────────────────────────────────────────────
def with_timeout(timeout_seconds: int):
    """给任意函数加超时，被 TimeoutError 视为失败。"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            with ThreadPoolExecutor(max_workers=1) as exc:
                future = exc.submit(func, *args, **kwargs)
                try:
                    return future.result(timeout=timeout_seconds)
                except FuturesTimeoutError:
                    raise TimeoutError(f"[{func.__name__}] 执行超时（{timeout_seconds}s）")
        return wrapper
    return decorator


# ── State ─────────────────────────────────────────────────────────────────────
class PipelineState(TypedDict):
    topic:            str
    research_results: Union[Dict[str, Any], None]
    pending_videos:   Annotated[list[str], lambda a, b: a + b]
    completed_videos: Annotated[list[Dict[str, Any]], lambda a, b: a + b]
    failed_videos:    Annotated[list[str], lambda a, b: a + b]
    summaries:        Annotated[list[Dict[str, Any]], lambda a, b: a + b]
    book_draft:       Union[str, None]
    output_files:     Union[Dict[str, str], None]
    step:             Literal["idle", "researching", "awaiting_review", "transcribing", "summarizing", "integrating", "done", "error"]
    error:            Union[str, None]
    _dispatched:      Annotated[list[str], lambda a, b: a + b]   # 防重复分发
    review_status:    Literal["pending", "approved", "rejected", "timeout", "none"]  # none=跳审核
    approved_videos:  Annotated[list[str], lambda a, b: a + b]
    rejected_videos: Annotated[list[str], lambda a, b: a + b]
    thread_id:        str


# ── 工具函数 ─────────────────────────────────────────────────────────────────
def _feishu_notify(text: str, thread_id: str) -> bool:
    """发飞书文本消息到 DM 频道，返回是否成功。"""
    feishu_token = os.environ.get("FEISHU_APP_SECRET", "")
    app_id       = os.environ.get("FEISHU_APP_ID", "cli_a957b23b43b89bdf")

    if not feishu_token:
        # 尝试从 keychain 读取
        try:
            import subprocess
            result = subprocess.run(
                ["security", "find-generic-password", "-s", "feishu", "-w"],
                capture_output=True, text=True, timeout=5
            )
            feishu_token = result.stdout.strip()
        except Exception:
            pass

    # 获取 tenant_access_token
    try:
        import requests
        token_resp = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": feishu_token},
            timeout=10
        )
        token_resp.raise_for_status()
        token = token_resp.json().get("tenant_access_token", "")
        if not token:
            print(f"[Feishu] 获取 token 失败: {token_resp.json()}")
            return False

        payload = {
            "receive_id": "oc_dd99d0b9523e7c8ae5d9883222fdc2cb",
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }
        resp = requests.post(
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload, timeout=15
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[Feishu] 发送失败: {e}")
        return False


# ── Node: AI 搜集 ─────────────────────────────────────────────────────────
@with_timeout(TIMEOUT_RESEARCH)
def node_research(state: PipelineState) -> Dict[str, Any]:
    # --urls 注入时跳过 research，直接进入审核节点（审核标记为 none）
    if state.get("pending_videos") and not state.get("research_results"):
        print(f"[Node: research] 跳过（已有 {len(state['pending_videos'])} 个视频由 --urls 注入）")
        return {
            "step": "awaiting_review",
            "review_status": "none",
            "_dispatched": [],
        }

    topic = state["topic"]
    print(f"\n[Node: research] 搜集 '{topic}' 相关资料...")

    try:
        search_prompt = f'''你是一个视频推荐专家。为主题「{topic}」推荐 3-5 个最相关的 B站（bilibili.com）或 YouTube（youtube.com）视频。

要求：
- 只推荐真实存在的视频链接
- 优先选择播放量高、内容精准的视频
- B站链接格式如：https://www.bilibili.com/video/BV1xx411xx/
- YouTube 链接格式如：https://www.youtube.com/watch?v=xxxxxx

返回纯 JSON 数组：
[
  {{"title": "视频标题", "url": "视频链接", "platform": "bilibili/youtube", "note": "一句话推荐理由"}}
]

只返回 JSON，不要其他内容。'''

        raw = llm_minimax(search_prompt, timeout=TIMEOUT_RESEARCH - 10)
        json_match = re.search(r"\[[\s\S]*\]", raw)
        try:
            selected = json.loads(json_match.group()) if json_match else []
        except Exception:
            selected = []

        video_urls = []
        for v in selected:
            url = v.get("url", "") if isinstance(v, dict) else str(v)
            if url and ("bilibili.com" in url or "youtube.com" in url):
                video_urls.append(url)

        print(f"[Node: research] 完成：找到 {len(video_urls)} 个视频")

        # 保存研究结果
        safe_topic = "".join(c if c.isalnum() or c in " -_" else "_" for c in topic)[:30]
        research_output = OUTPUT_RESEARCH / safe_topic
        research_output.mkdir(parents=True, exist_ok=True)
        (research_output / "research_results.json").write_text(
            json.dumps({"topic": topic, "selected_videos": selected, "video_urls": video_urls}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        return {
            "research_results": {"topic": topic, "selected_videos": video_urls},
            "pending_videos":   video_urls,
            "step":             "awaiting_review",
            "review_status":    "pending",
            "_dispatched":      [],
            "approved_videos":  [],
            "rejected_videos":  [],
        }

    except TimeoutError as e:
        print(f"[Node: research] 超时: {e}")
        return {"step": "error", "error": f"研究阶段超时（{TIMEOUT_RESEARCH}s）：{e}"}
    except Exception as e:
        print(f"[Node: research] 失败: {e}")
        return {"step": "error", "error": f"研究失败: {e}"}


# ── Node: 发送审核请求 ───────────────────────────────────────────────────────
def node_send_review_request(state: PipelineState) -> Dict[str, Any]:
    """
    将 LLM 推荐视频列表整理成飞书消息，发送给用户。
    然后触发 Interrupt，等待 Hermes approve/reject 命令唤醒。
    """
    import time
    thread_id = state.get("thread_id", "default")
    videos    = state.get("pending_videos", [])
    review_st = state.get("review_status", "pending")

    # --urls 模式：review_status=none，跳过审核直接放行
    if review_st == "none":
        print("[Node: send_review_request] --urls 模式，跳过审核，直接进入转录")
        return {"step": "transcribing", "_dispatched": []}

    # 格式化视频列表
    lines = [f"🎬 **视频审核请求**（主题：{state['topic']}）", ""]
    for i, url in enumerate(videos, 1):
        lines.append(f"{i}. {url}")
    lines.append("")
    lines.append("回复 `approve` 全部通过，或 `reject` 全部拒绝，或 `modify: 去掉某几个` 修改")

    text = "\n".join(lines)
    _feishu_notify(text, thread_id)

    # 持久化审核状态（把待审核视频存进 approved_videos 字段，approve 时自动全部批准）
    _save_review(thread_id, "pending", approved=videos, rejected=[])
    print(f"[Node: send_review_request] 已发送审核请求到飞书，等待用户响应...")

    # 触发 Interrupt，LangGraph 暂停在此处
    # Interrupt 的 value 会通过 run.py approve/reject 命令覆盖 DB 后再 resume
    raise NodeInterrupt(
        f"等待人工审核视频列表，请回复 approve/reject（1小时后自动拒绝）：\n{text}",
        id="video-review",
    )


# ── Node: 等待审核结果（resume 时进入）─────────────────────────────────────────
def node_wait_review(state: PipelineState) -> Dict[str, Any]:
    """
    Interrupt 恢复后从此节点继续。
    读取 review DB，获取用户批准/拒绝结果。
    """
    import time
    thread_id = state.get("thread_id", "default")
    status, approved, rejected = _get_review(thread_id)

    print(f"[Node: wait_review] 审核结果: {status}")

    if status == "pending":
        # 超时未审核，当作拒绝处理
        status = "timeout"
        _save_review(thread_id, "timeout")
        print("[Node: wait_review] 审核超时，自动拒绝")

    if status in ("rejected", "timeout"):
        print("[Node: wait_review] 用户拒绝/超时，Pipeline 终止")
        return {
            "step": "done",
            "pending_videos": [],
            "review_status": status,
            "approved_videos": [],
            "rejected_videos": state.get("pending_videos", []),
        }

    # approved：过滤掉用户拒绝的视频
    if approved:
        final_videos = approved
    else:
        final_videos = state.get("pending_videos", [])

    print(f"[Node: wait_review] 审核通过，{len(final_videos)}/{len(state.get('pending_videos',[]))} 个视频进入转录")

    return {
        "step":             "transcribing",
        "review_status":    status,
        "pending_videos":    final_videos,
        "approved_videos":  approved,
        "rejected_videos":  rejected,
        "_dispatched":       [],   # 重置分发记录
    }


# ── Node: dispatcher ─────────────────────────────────────────────────────────
def node_dispatcher(state: PipelineState) -> Dict[str, Any]:
    """纯分发器 node：只记录，不更新 state（返回空 dict）。"""
    dispatched = set(state.get("_dispatched", []))
    pending    = [v for v in state["pending_videos"] if v not in dispatched]
    if pending:
        print(f"[Node: dispatcher] 待分发: {len(pending)} 个视频 "
              f"（累计完成 {len(state['completed_videos'])}/{len(state['pending_videos'])}）")
    return {}   # dispatcher node 不更新 state


# ── Conditional Edge: route_dispatcher ────────────────────────────────────────
def route_dispatcher(state: PipelineState) -> str | list:
    """
    路由函数：返回 str 或 List[Send]。
    List[Send] 只能从这里返回，不能从任何 node 函数返回。
    """
    dispatched = set(state.get("_dispatched", []))
    pending    = [v for v in state["pending_videos"] if v not in dispatched]

    if not pending:
        print("[Edge: route_dispatcher] 无待处理视频，进入整合")
        return "summarize_aggregator"

    print(f"[Edge: route_dispatcher] 分发 {len(pending)} 个 Send 到 transcribe_single")
    return [
        Send("transcribe_single", {"video": video, "idx": len(dispatched) + i, "topic": state.get("topic", "")})
        for i, video in enumerate(pending)
    ]


# ── Node: transcribe_single ──────────────────────────────────────────────────
@with_timeout(TIMEOUT_DOWNLOAD + TIMEOUT_TRANSCRIBE + TIMEOUT_SUMMARIZE + 30)
def node_transcribe_single(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    并行子图节点：下载视频 → 转录 → 总结。
    整体有总超时保护，内部各步骤也有独立超时。
    """
    video = state["video"]
    idx   = state.get("idx", 0)
    topic = state.get("topic", "unknown")
    print(f"[Node: transcribe_single:{idx}] 处理: {video[:60]}")

    # 每个视频的任务独立子目录
    video_output = OUTPUT_TRANSCRIBE / f"task-{idx}"
    video_output.mkdir(parents=True, exist_ok=True)

    try:
        # Step 1: 下载（带超时）
        from video_download import download

        @with_timeout(TIMEOUT_DOWNLOAD)
        def _download():
            return download(url=video, output_dir=str(video_output), quality="audio_only", subtitle_only=False)

        dl = _download()

        if not dl.get("success"):
            raise RuntimeError(f"下载失败: {dl.get('error', 'unknown')}")

        file_path     = dl.get("file_path", "")
        duration      = dl.get("duration", 0)
        subtitle_path = dl.get("subtitle_path", "")
        dl_method     = dl.get("method", "download")
        title         = dl.get("title", video)
        print(f"[Node: transcribe_single:{idx}] 下载完成: {file_path} ({dl_method})")

        # Step 2: 转录
        from audio_transcribe import transcribe

        if subtitle_path and dl_method == "subtitle":
            srt_path = subtitle_path
            print(f"[Node: transcribe_single:{idx}] 使用直取字幕: {srt_path}")
        else:
            if not file_path:
                raise RuntimeError("下载未返回文件路径")

            @with_timeout(TIMEOUT_TRANSCRIBE)
            def _transcribe():
                return transcribe(file_path, str(video_output))

            result = _transcribe()
            srt_path = result.get("srt_path", "")
            if not srt_path:
                raise RuntimeError("转录未返回 srt_path")
            print(f"[Node: transcribe_single:{idx}] 转录完成: {srt_path}")

        # Step 3: 总结
        from whisper_summarizer import summarize

        @with_timeout(TIMEOUT_SUMMARIZE)
        def _summarize():
            return summarize(srt_path, output_path=str(video_output / "summary.json"))

        summary_result = _summarize()
        summary_text   = summary_result.get("summary", "")
        print(f"[Node: transcribe_single:{idx}] 总结完成，长度: {len(summary_text)}")

        return {
            "completed_videos": [{
                "url": video, "title": title, "file_path": file_path,
                "srt_path": srt_path, "summary": summary_text, "duration": duration,
            }],
            "summaries":      [{"video": video, "title": title, "summary": summary_text}],
            "failed_videos":   [],
            "_dispatched":     [video],
        }

    except TimeoutError as e:
        print(f"[Node: transcribe_single:{idx}] 超时: {e}")
        return {"completed_videos": [], "failed_videos": [video], "_dispatched": [video]}
    except FileNotFoundError:
        print(f"[Node: transcribe_single:{idx}] 文件不存在: {video[:60]}")
        return {"completed_videos": [], "failed_videos": [video], "_dispatched": [video]}
    except Exception as e:
        print(f"[Node: transcribe_single:{idx}] 错误: {e}")
        return {"completed_videos": [], "failed_videos": [video], "_dispatched": [video]}


# ── Node: summarize_aggregator ──────────────────────────────────────────────
@with_timeout(TIMEOUT_INTEGRATE)
def node_summarize_aggregator(state: PipelineState) -> Dict[str, Any]:
    summaries = state["summaries"]
    print(f"[Node: summarize_aggregator] 整合 {len(summaries)} 个总结...")

    if not summaries:
        print("[Node: summarize_aggregator] 无总结内容，跳过")
        return {"step": "summarizing"}

    summaries_text = "\n\n".join(
        f"=== 视频 {i+1}: {s.get('video', '')[:50]} ===\n{s.get('summary', '')}"
        for i, s in enumerate(summaries)
    )

    try:
        prompt = f'''你是一个专业的内容整合专家。请将以下多个视频的总结整合成一份结构化的综合报告：

{summaries_text}

请按以下格式输出：
## 综合主题
## 核心观点（按主题分类）
## 各部分详细内容
## 行动建议

只需返回报告正文。'''
        integrated = llm_minimax(prompt, timeout=TIMEOUT_INTEGRATE - 10)
        print(f"[Node: summarize_aggregator] 整合完成，长度: {len(integrated)}")
        return {"book_draft": integrated, "step": "summarizing"}
    except TimeoutError as e:
        print(f"[Node: summarize_aggregator] 超时: {e}，使用原始总结代替")
        return {"book_draft": summaries_text, "step": "summarizing"}
    except Exception as e:
        print(f"[Node: summarize_aggregator] LLM 整合失败: {e}")
        return {"book_draft": summaries_text, "step": "summarizing"}


# ── Node: write_book ─────────────────────────────────────────────────────────
@with_timeout(TIMEOUT_WRITE_BOOK)
def node_write_book(state: PipelineState) -> Dict[str, Any]:
    topic = state["topic"]
    draft = state.get("book_draft") or ""
    print(f"[Node: write_book] 生成书稿...")

    if not draft:
        draft = f"# {topic}\n\n（内容待整合）"

    try:
        prompt = f'''你是一个专业作家。请将以下草稿扩展成一本结构完整、内容翔实的电子书。

主题：{topic}

草稿：
{draft}

请生成书籍目录结构和各章节详细内容，至少 5 章，每章有实质性内容。总字数不少于 2000 字。只需返回书籍正文。'''
        book = llm_minimax(prompt, timeout=TIMEOUT_WRITE_BOOK - 10)
        print(f"[Node: write_book] 书稿完成，长度: {len(book)}")
        return {"book_draft": book, "step": "integrating"}
    except TimeoutError as e:
        print(f"[Node: write_book] 超时: {e}，使用草稿代替")
        return {"book_draft": draft, "step": "integrating"}
    except Exception as e:
        print(f"[Node: write_book] 失败: {e}")
        return {"book_draft": draft, "step": "integrating"}


# ── Node: notify ─────────────────────────────────────────────────────────────
def node_notify(state: PipelineState) -> Dict[str, Any]:
    topic = state["topic"]
    book  = state.get("book_draft") or ""

    safe_topic  = "".join(c if c.isalnum() or c in " -_" else "_" for c in topic)[:20]
    output_file = OUTPUT_BOOK / f"{safe_topic}_书稿.md"
    output_file.write_text(f"# {topic}\n\n{book}", encoding="utf-8")

    completed = len(state.get("completed_videos", []))
    failed    = len(state.get("failed_videos", []))
    print(f"[Node: notify] 书稿已保存: {output_file}")
    print(f"[Node: notify] 完成！转录 {completed} 个视频，失败 {failed} 个")

    # 发飞书完成通知
    msg = (f"✅ Pipeline 完成！主题：{topic}\n"
           f"转录成功：{completed} 个 | 失败：{failed} 个\n"
           f"书稿：{output_file}")
    _feishu_notify(msg, state.get("thread_id", "default"))

    return {
        "step":       "done",
        "output_files": {"book": str(output_file)},
    }


# ── 构建 Graph ───────────────────────────────────────────────────────────────
def build_graph():
    builder = StateGraph(PipelineState)

    builder.add_node("research",             node_research)
    builder.add_node("send_review_request", node_send_review_request)
    builder.add_node("wait_review",         node_wait_review)
    builder.add_node("dispatcher",          node_dispatcher)
    builder.add_node("transcribe_single",   node_transcribe_single)
    builder.add_node("summarize_aggregator", node_summarize_aggregator)
    builder.add_node("write_book",           node_write_book)
    builder.add_node("notify",              node_notify)

    # 主流程
    builder.add_edge(START, "research")

    builder.add_edge("research", "send_review_request")

    # send_review_request 的出边：--urls 跳审核直接进 dispatcher；正常则触发 Interrupt 后进 wait_review
    builder.add_conditional_edges(
        "send_review_request",
        lambda s: "dispatcher" if s.get("review_status") == "none" else "wait_review",
        {"wait_review": "wait_review", "dispatcher": "dispatcher"},
    )

    # Interrupt 恢复时从 wait_review 继续，审核通过后进 dispatcher
    builder.add_edge("wait_review", "dispatcher")

    # fan-out 循环
    builder.add_edge("transcribe_single", "dispatcher")

    # dispatcher → conditional edge
    builder.add_conditional_edges(
        "dispatcher",
        route_dispatcher,
        {"summarize_aggregator": "summarize_aggregator"},
    )

    builder.add_edge("summarize_aggregator", "write_book")
    builder.add_edge("write_book",          "notify")
    builder.add_edge("notify",              END)

    return builder.compile(
        checkpointer=_get_checkpointer(),
        debug=False,
    )


# ── 单例 ─────────────────────────────────────────────────────────────────────
_app = None


def get_app():
    global _app
    if _app is None:
        _app = build_graph()
    return _app


def list_threads():
    import sqlite3
    if not CHECKPOINT_DB.exists():
        return []
    conn = sqlite3.connect(str(CHECKPOINT_DB))
    rows = conn.execute(
        "SELECT DISTINCT thread_id FROM checkpoints ORDER BY thread_id"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


# ── 打印 ─────────────────────────────────────────────────────────────────────
def print_graph():
    print("""
┌──────────────────────────────────────────────────────────────────────┐
│              01-video-md Pipeline 架构图 (LangGraph v1.x)            │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  START ──▶ [research] ──▶ [send_review_request]                    │
│                                       │                              │
│                                       ▼  Interrupt 暂停             │
│                             （飞书通知 → Hermes 审核）               │
│                                       │                              │
│                                       ▼  approve/reject             │
│                                  [wait_review]                       │
│                                       │                              │
│                                       ▼                              │
│                                [dispatcher]                          │
│                                       │                              │
│                     ┌────────────────┴────────────────┐             │
│                     │  conditional edge               │             │
│                     │  route_dispatcher               │             │
│                     │  返回 List[Send]                │             │
│                     └────────────────┬────────────────┘             │
│                          │            │                            │
│         无待处理视频      │            │ List[Send]                  │
│              ▼           │            ▼                            │
│   [summarize_aggregator] │  [transcribe_single × N]                 │
│              │           │            │                            │
│              └───────────┴────────────┘                            │
│                         │ dispatcher 循环                           │
│                         ▼                                           │
│               [write_book] ──▶ [notify] ──▶ END                     │
└──────────────────────────────────────────────────────────────────────┘

新增机制：
  Interrupt   → 人工审核暂停点（research 后触发 Hermes 审核）
  超时保护    → 每个节点独立超时，超时自动标记 failed，不卡死
  审核 DB     → review_status.db 持久化审核结果，支持 approve/reject
  飞书通知    → 审核请求、完成通知自动推送到飞书 DM
""")


def print_state(state: Dict[str, Any]):
    step      = state.get("step", "?")
    completed = len(state.get("completed_videos", []))
    total     = len(state.get("pending_videos", []))
    summaries  = len(state.get("summaries", []))
    book_ready = bool(state.get("book_draft"))
    output    = state.get("output_files")
    error     = state.get("error")
    review    = state.get("review_status", "none")
    failed    = len(state.get("failed_videos", []))

    step_emoji = {
        "idle": "⏳", "researching": "🔍", "awaiting_review": "👀",
        "transcribing": "🎬", "summarizing": "📝", "integrating": "📖",
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
