"""transcribe_subgraph 三个节点实现。

节点拆成三个独立函数是为了：
  - 每步失败独立重试
  - 每步有独立超时
  - State 清晰展示中间产物
  - 未来某一步换实现不影响其他

所有 IO 走工具函数（_do_download/_do_transcribe/_do_summarize），
node 只做编排 + State 更新。

字幕优先策略（use_subtitle_first=True）：
  1. 先用 opencli bilibili subtitle 取字幕 → 有字幕直接用，跳过 Whisper
  2. 字幕缺失或命令失败 → 下载音频 → Whisper 转录
"""
from __future__ import annotations
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Any, Optional

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


def _find_opencli(config: TranscribeConfig) -> Optional[str]:
    """查找 opencli 可执行文件路径（优先 Node 22）。"""
    if config.opencli_bin:
        return config.opencli_bin
    candidates = [
        "/Users/zyongzhu/.nvm/versions/node/v22.22.2/bin/opencli",
        shutil.which("opencli"),
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return None


def _extract_bvid(url: str) -> Optional[str]:
    """从 B 站 URL 提取 BV 号。"""
    m = re.search(r"BV\w+", url)
    return m.group(0) if m else None


def _opencli_get_subtitle(url: str, config: TranscribeConfig, out_dir: Path, idx: int) -> Optional[str]:
    """
    用 opencli bilibili subtitle 取字幕，保存为 SRT，返回路径。
    失败时返回 None（降级到 Whisper）。
    """
    bvid = _extract_bvid(url)
    if not bvid:
        return None

    opencli = _find_opencli(config)
    if not opencli:
        return None

    # 保证用 Node 22 运行
    node22_bin = str(Path(opencli).parent)
    env = os.environ.copy()
    env["PATH"] = f"{node22_bin}:{env.get('PATH', '')}"

    try:
        result = subprocess.run(
            [opencli, "bilibili", "subtitle", bvid, "--format", "json"],
            capture_output=True, text=True, timeout=30, env=env,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None

        items = json.loads(result.stdout)
        if not items:
            return None   # 视频无字幕

        # 把 opencli 的 JSON 字幕转换成 SRT 格式
        srt_lines = []
        for item in items:
            idx_n = item.get("index", 0)
            from_t = item.get("from", "0.00s").replace("s", "")
            to_t = item.get("to", "0.00s").replace("s", "")
            content = item.get("content", "")

            def sec_to_srt(s: str) -> str:
                try:
                    sec = float(s)
                    h = int(sec // 3600)
                    m = int((sec % 3600) // 60)
                    sc = sec % 60
                    return f"{h:02d}:{m:02d}:{sc:06.3f}".replace(".", ",")
                except Exception:
                    return "00:00:00,000"

            srt_lines.append(str(idx_n))
            srt_lines.append(f"{sec_to_srt(from_t)} --> {sec_to_srt(to_t)}")
            srt_lines.append(content)
            srt_lines.append("")

        srt_path = out_dir / f"subtitle_{bvid}.srt"
        srt_path.write_text("\n".join(srt_lines), encoding="utf-8")
        print(f"[transcribe:{idx}] ✅ opencli 字幕获取成功（{len(items)} 条），跳过 Whisper")
        return str(srt_path)

    except subprocess.TimeoutExpired:
        print(f"[transcribe:{idx}] opencli subtitle 超时，降级到 Whisper")
        return None
    except Exception as e:
        print(f"[transcribe:{idx}] opencli subtitle 失败: {e}，降级到 Whisper")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# Node 1: download（字幕优先）
# ═══════════════════════════════════════════════════════════════════════════
def make_download_node(config: TranscribeConfig):
    """工厂：注入 config，返回 download node。

    字幕优先策略（use_subtitle_first=True）：
      1. 先用 opencli 取 B 站字幕 → 有字幕直接跳过音频下载和 Whisper
      2. 字幕失败/无字幕 → 正常下载音频
    """

    def download_node(state: TranscribeState) -> Dict[str, Any]:
        video_url = state.get("video_url", "")
        idx = state.get("task_idx", 0)
        if not video_url:
            return {"success": False, "error": "video_url 为空"}

        out_dir = _task_dir(config, idx)

        # ── 路径 1：opencli 字幕优先（B 站 + 已开启字幕优先） ──────────────
        if config.use_subtitle_first and "bilibili.com" in video_url:
            print(f"[transcribe:{idx}] 尝试 opencli 字幕: {video_url[:60]}")
            srt_path = _opencli_get_subtitle(video_url, config, out_dir, idx)
            if srt_path:
                # 有字幕：跳过下载和 Whisper，直接带 srt_path 返回
                bvid = _extract_bvid(video_url) or video_url
                return {
                    "file_path": "",
                    "subtitle_path": srt_path,
                    "srt_path": srt_path,           # 直接设置，transcribe node 会检测到跳过
                    "download_method": "subtitle",
                    "title": bvid,
                    "duration": 0,
                }
            print(f"[transcribe:{idx}] 无字幕，降级到音频下载+Whisper")

        # ── 路径 2：下载音频 → Whisper 转录 ───────────────────────────────
        _ensure_tools_loaded(config.tools_src)
        print(f"[transcribe:{idx}] 下载音频: {video_url[:60]}")

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

        # 字幕已在 download node 设置好（opencli 路径），直接跳过
        if state.get("srt_path"):
            print(f"[transcribe:{idx}] 字幕已就绪，跳过 Whisper")
            return {}

        subtitle_path = state.get("subtitle_path", "")
        file_path = state.get("file_path", "")
        method = state.get("download_method", "")

        # 历史兼容：旧的直取字幕路径
        if subtitle_path and method == "subtitle":
            print(f"[transcribe:{idx}] 使用直取字幕: {subtitle_path}")
            return {"srt_path": subtitle_path}

        # Whisper 转录
        if not file_path:
            return {"success": False, "error": "下载未返回文件路径"}

        _ensure_tools_loaded(config.tools_src)
        out_dir = _task_dir(config, idx)

        print(f"[transcribe:{idx}] Whisper 转录（无字幕视频）...")

        try:
            from audio_transcribe import transcribe  # type: ignore

            @with_timeout(config.timeout_transcribe)
            def _do_transcribe():
                return transcribe(file_path, str(out_dir))

            result = _do_transcribe()
            srt_path = result.get("srt_path", "")
            if not srt_path:
                return {"success": False, "error": "转录未返回 srt_path"}

            print(f"[transcribe:{idx}] Whisper 转录完成: {srt_path}")
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
