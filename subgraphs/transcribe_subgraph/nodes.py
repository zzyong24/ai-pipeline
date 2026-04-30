"""transcribe_subgraph 三个节点实现。

节点拆成三个独立函数是为了：
  - 每步失败独立重试
  - 每步有独立超时
  - State 清晰展示中间产物
  - 未来某一步换实现不影响其他

所有 IO 走工具函数（_do_download/_do_transcribe/_do_summarize），
node 只做编排 + State 更新。
"""
from __future__ import annotations
import sys
from pathlib import Path
from typing import Dict, Any

from ..shared.timeout import with_timeout
from ..shared.observability import obs_span
from .state import TranscribeState
from .config import TranscribeConfig


def _ensure_tools_loaded(tools_src: Path | None):
    """把 tools_src 加到 sys.path（懒加载）。"""
    if tools_src and str(tools_src) not in sys.path:
        sys.path.insert(0, str(tools_src))


def _task_dir(config: TranscribeConfig, idx: int) -> Path:
    """按任务索引产出独立目录，避免并行冲突。"""
    base = config.output_base or Path.cwd() / "output" / "transcribe"
    target = base / f"task-{idx}"
    target.mkdir(parents=True, exist_ok=True)
    return target


# ═══════════════════════════════════════════════════════════════════════════
# Node 1: download
# ═══════════════════════════════════════════════════════════════════════════
def make_download_node(config: TranscribeConfig):
    """工厂：注入 config，返回 download node。"""

    def download_node(state: TranscribeState) -> Dict[str, Any]:
        video_url = state.get("video_url", "")
        idx = state.get("task_idx", 0)
        if not video_url:
            return {"success": False, "error": "video_url 为空"}

        _ensure_tools_loaded(config.tools_src)
        out_dir = _task_dir(config, idx)

        print(f"[transcribe:{idx}] 下载: {video_url[:60]}")

        try:
            from video_download import download  # type: ignore

            @with_timeout(config.timeout_download)
            def _do_download():
                return download(
                    url=video_url,
                    output_dir=str(out_dir),
                    quality="audio_only",
                    subtitle_only=False,
                )

            dl = _do_download()
            if not dl.get("success"):
                return {"success": False, "error": f"下载失败: {dl.get('error', 'unknown')}"}

            return {
                "file_path": dl.get("file_path", ""),
                "subtitle_path": dl.get("subtitle_path", ""),
                "download_method": dl.get("method", "download"),
                "title": dl.get("title", video_url),
                "duration": dl.get("duration", 0),
            }

        except TimeoutError as e:
            return {"success": False, "error": f"下载超时: {e}"}
        except Exception as e:
            return {"success": False, "error": f"下载错误: {e}"}

    return download_node


# ═══════════════════════════════════════════════════════════════════════════
# Node 2: transcribe
# ═══════════════════════════════════════════════════════════════════════════
def make_transcribe_node(config: TranscribeConfig):
    """工厂：注入 config，返回 transcribe node。"""

    def transcribe_node(state: TranscribeState) -> Dict[str, Any]:
        # 已失败则跳过（保留 error）
        if state.get("error"):
            return {}

        idx = state.get("task_idx", 0)
        subtitle_path = state.get("subtitle_path", "")
        file_path = state.get("file_path", "")
        method = state.get("download_method", "")

        # 路径 1：直取字幕
        if subtitle_path and method == "subtitle":
            print(f"[transcribe:{idx}] 使用直取字幕: {subtitle_path}")
            return {"srt_path": subtitle_path}

        # 路径 2：本地转录
        if not file_path:
            return {"success": False, "error": "下载未返回文件路径"}

        _ensure_tools_loaded(config.tools_src)
        out_dir = _task_dir(config, idx)

        try:
            from audio_transcribe import transcribe  # type: ignore

            @with_timeout(config.timeout_transcribe)
            def _do_transcribe():
                return transcribe(file_path, str(out_dir))

            result = _do_transcribe()
            srt_path = result.get("srt_path", "")
            if not srt_path:
                return {"success": False, "error": "转录未返回 srt_path"}

            print(f"[transcribe:{idx}] 转录完成: {srt_path}")
            return {"srt_path": srt_path}

        except TimeoutError as e:
            return {"success": False, "error": f"转录超时: {e}"}
        except Exception as e:
            return {"success": False, "error": f"转录错误: {e}"}

    return transcribe_node


# ═══════════════════════════════════════════════════════════════════════════
# Node 3: summarize
# ═══════════════════════════════════════════════════════════════════════════
def make_summarize_node(config: TranscribeConfig):
    """工厂：注入 config，返回 summarize node。"""

    def summarize_node(state: TranscribeState) -> Dict[str, Any]:
        # 已失败则跳过
        if state.get("error"):
            return {"success": False}

        idx = state.get("task_idx", 0)
        srt_path = state.get("srt_path", "")
        if not srt_path:
            return {"success": False, "error": "srt_path 为空"}

        _ensure_tools_loaded(config.tools_src)
        out_dir = _task_dir(config, idx)
        trace_span = state.get("_trace_span")

        try:
            from whisper_summarizer import summarize  # type: ignore

            @with_timeout(config.timeout_summarize)
            def _do_summarize():
                return summarize(srt_path, output_path=str(out_dir / "summary.json"))

            with obs_span(trace_span, "transcribe/summarize") as s:
                result = _do_summarize()

            summary_text = result.get("summary", "")
            print(f"[transcribe:{idx}] 总结完成，长度: {len(summary_text)}")

            return {
                "summary": summary_text,
                "success": True,
                "error": None,
            }

        except TimeoutError as e:
            return {"success": False, "error": f"总结超时: {e}"}
        except Exception as e:
            return {"success": False, "error": f"总结错误: {e}"}

    return summarize_node
