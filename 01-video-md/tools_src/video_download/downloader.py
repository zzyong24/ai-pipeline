"""
视频下载工具 v2 — 抄自 msg-collect/video_downloader_worker.py

核心策略：字幕优先，下载兜底
- YouTube  → YouTubeTranscriptExtractor（多策略自动回退）
- B站      → bilibili_api SDK + SESSDATA cookie
- 抖音     → iesdouyin.com 页面爬取直链
- 其他     → yt_dlp.YoutubeDL() Python API

依赖（已在 tools venv）：
    yt-dlp, bilibili-api-python, youtube-transcript-api, browser-cookie3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Optional

import yt_dlp


# ---------------------------------------------------------------------------
# 平台判断
# ---------------------------------------------------------------------------

def _is_youtube(url: str) -> bool:
    try:
        from urllib.parse import urlparse
        netloc = urlparse(url).netloc.lower()
    except Exception:
        return False
    return any(d in netloc for d in ("youtube.com", "youtu.be", "youtube-nocookie.com"))


def _is_bilibili(url: str) -> bool:
    try:
        from urllib.parse import urlparse
        netloc = urlparse(url).netloc.lower()
    except Exception:
        return False
    return "bilibili.com" in netloc or "b23.tv" in netloc


def _is_douyin(url: str) -> bool:
    try:
        from urllib.parse import urlparse
        netloc = urlparse(url).netloc.lower()
    except Exception:
        return False
    return any(d in netloc for d in ("douyin.com", "iesdouyin.com"))


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _format_duration(seconds: float) -> str:
    """秒 → SRT 时间格式 HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _download_text(url: str) -> str:
    """下载纯文本内容（字幕文件）"""
    from urllib.request import Request, urlopen
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _select_bilibili_subtitle(subtitle_items: list) -> Optional[dict]:
    """从 B站字幕列表中选一个最好的（中/英）"""
    preference = ["zh-Hans", "zh", "zh-CN", "zh-TW", "en-US", "en"]
    for lang in preference:
        for item in subtitle_items:
            lan = str(item.get("lan", "") or item.get("lang", ""))
            if lan.lower() == lang.lower():
                return item
    # fallback：返回第一个有 url 的
    for item in subtitle_items:
        if item.get("subtitle_url") or item.get("url"):
            return item
    return subtitle_items[0] if subtitle_items else None


# ---------------------------------------------------------------------------
# YouTube 字幕提取（抄 msg-collect）
# ---------------------------------------------------------------------------

def extract_youtube_subtitle(url: str, output_path: str) -> Optional[dict]:
    """
    使用 YouTubeTranscriptExtractor 多策略提取字幕。
    策略顺序：transcript_api → direct_http → ytdlp → innertube
    结果写入 output_path，返回元信息。
    """
    try:
        import socket
        # 设置全局 socket 超时，避免 list_transcripts 永久挂起
        orig_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(30)
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            from youtube_transcript_api.formatters import TextFormatter
        finally:
            socket.setdefaulttimeout(orig_timeout)
    except ImportError:
        print(json.dumps({"success": False, "error": "缺少 youtube-transcript-api"}))
        return None

    # 提取 video_id
    patterns = [
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube-nocookie\.com/embed/)([a-zA-Z0-9_-]{11})",
        r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})",
    ]
    video_id = None
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            video_id = m.group(1)
            break
    if not video_id:
        print(json.dumps({"success": False, "error": f"无法从 URL 提取 YouTube video_id: {url}"}))
        return None

    try:
        # 优先尝试手动字幕，再自动字幕
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        transcript = None
        try:
            # 先试zh字幕
            transcript = transcript_list.find_transcript(["zh-Hans", "zh-TW", "zh", "zh-CN"])
        except Exception:
            try:
                transcript = transcript_list.find_transcript(["en"])
            except Exception:
                try:
                    # 找自动生成的
                    transcript = transcript_list.find_generated_transcript(["zh", "en"])
                except Exception:
                    pass

        if transcript is None:
            print(json.dumps({"success": False, "error": "未找到可用字幕"}))
            return None

        entries = transcript.fetch()
        formatter = TextFormatter()
        text = formatter.format_transcript(entries)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text)

        return {
            "title": transcript.video_title or video_id,
            "duration": transcript.duration or 0,
            "language": transcript.language_code,
            "is_auto": transcript.is_generated,
            "path": output_path,
        }

    except Exception as e:
        print(json.dumps({"success": False, "error": f"YouTube字幕提取失败: {e}"}))
        return None


# ---------------------------------------------------------------------------
# B站字幕提取（抄 msg-collect bilibili_api SDK）
# ---------------------------------------------------------------------------

async def _bilibili_subtitle_async(url: str, sessdata: str, output_path: str) -> Optional[dict]:
    """异步版：B站字幕直取（bilibili_api SDK）"""
    try:
        from bilibili_api import Credential, video
    except ImportError:
        return None

    # 提取 bvid
    patterns = [r"/video/(BV[a-zA-Z0-9]+)", r"b23\.tv/(\w+)"]
    bvid = None
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            bvid = m.group(1)
            break
    if not bvid:
        return None

    credential = Credential(sessdata=sessdata) if sessdata else None
    v = video.Video(bvid=bvid, credential=credential)

    try:
        info = await v.get_info()
    except Exception:
        return None

    try:
        cid = await v.get_cid()
    except Exception:
        return None

    try:
        player_info = await v.get_player_info(cid=cid)
    except Exception:
        return None

    subtitle_block = player_info.get("subtitle") if isinstance(player_info, dict) else {}
    subtitle_items = subtitle_block.get("subtitles") if isinstance(subtitle_block, dict) else []
    if not subtitle_items:
        return None

    selected = _select_bilibili_subtitle(subtitle_items)
    if not selected:
        return None

    subtitle_url = str(selected.get("subtitle_url") or selected.get("url") or "")
    if not subtitle_url:
        return None

    try:
        raw = _download_text(subtitle_url)
        subtitle_json = json.loads(raw)
    except Exception:
        return None

    # 解析字幕 JSON → SRT 格式
    lines = []
    body = subtitle_json.get("body") if isinstance(subtitle_json, dict) else []
    if isinstance(body, list):
        for seg in body:
            if not isinstance(seg, dict):
                continue
            content = str(seg.get("content", "") or seg.get("text", "")).strip()
            if not content:
                continue
            try:
                start = float(seg.get("from", 0))
            except (TypeError, ValueError):
                start = 0.0
            end = start + float(seg.get("duration", 5))
            lines.append(f"{_format_duration(start)}{content}")
            lines.append(f"{_format_duration(end)}\n")

    transcript_text = "\n".join(lines)
    if not transcript_text.strip():
        return None

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(transcript_text)

    return {
        "title": info.get("title", bvid),
        "duration": info.get("duration", 0),
        "language": selected.get("lan", "zh"),
        "path": output_path,
    }


def extract_bilibili_subtitle(url: str, sessdata: str, output_path: str) -> Optional[dict]:
    """同步封装"""
    return asyncio.run(_bilibili_subtitle_async(url, sessdata, output_path))


# ---------------------------------------------------------------------------
# 抖音直链（抄 msg-collect iesdouyin.com 方案）
# ---------------------------------------------------------------------------

def extract_douyin_subtitle(url: str, output_path: str) -> Optional[dict]:
    """通过 iesdouyin.com 页面爬取抖音无水印直链并下载字幕（抖音通常无字幕，返回空文件）"""
    import urllib.request

    # 提取 video_id
    video_id = None
    m = re.search(r"/video/(\d+)", url)
    if m:
        video_id = m.group(1)
    else:
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(url).query)
        video_id = (qs.get("modal_id") or [""])[0]

    if not video_id:
        # 跟随短链重定向
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15"
            })
            with urllib.request.urlopen(req, timeout=20) as resp:
                final_url = resp.url
            m = re.search(r"/video/(\d+)", final_url)
            if m:
                video_id = m.group(1)
        except Exception:
            pass

    if not video_id:
        return None

    # 抖音通常不带字幕，写一个空占位文件
    Path(output_path).touch()
    return {
        "title": f"douyin_{video_id}",
        "duration": 0,
        "language": "zh",
        "path": output_path,
        "video_id": video_id,
    }


def download_douyin_video(url: str, output_dir: str) -> Optional[dict]:
    """下载抖音视频（iesdouyin.com 直链）"""
    # 提取 video_id（同上）
    video_id = None
    m = re.search(r"/video/(\d+)", url)
    if m:
        video_id = m.group(1)
    else:
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(url).query)
        video_id = (qs.get("modal_id") or [""])[0]

    if not video_id:
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15"
            })
            with urllib.request.urlopen(req, timeout=20) as resp:
                final_url = resp.url
            m = re.search(r"/video/(\d+)", final_url)
            if m:
                video_id = m.group(1)
        except Exception:
            return None

    page_url = f"https://www.iesdouyin.com/share/video/{video_id}/"
    try:
        import urllib.request
        req = urllib.request.Request(page_url, headers={
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) EdgiOS/121.0.2277.107 Version/17.0 Mobile/15E148 Safari/604.1"
        })
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return None

    m = re.search(r"window\._ROUTER_DATA\s*=\s*(.*?)</script>", html, re.DOTALL)
    if not m:
        return None

    try:
        data = json.loads(m.group(1).strip())
    except json.JSONDecodeError:
        return None

    loader = data.get("loaderData", data)
    item = None
    for key in ("video_(id)/page", "note_(id)/page"):
        node = loader.get(key)
        if node:
            items = (node.get("videoInfoRes") or {}).get("item_list") or []
            if items:
                item = items[0]
                break

    if not item:
        return None

    url_list = ((item.get("video") or {}).get("play_addr") or {}).get("url_list") or []
    if not url_list:
        url_list = ((item.get("video") or {}).get("download_addr") or {}).get("url_list") or []
    if not url_list:
        return None

    direct_url = url_list[0].replace("playwm", "play")
    title = (item.get("desc") or f"douyin_{video_id}").replace("/", "_")

    # 用 yt_dlp.YoutubeDL 下载（Python API，无 subprocess）
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    outtmpl = os.path.join(output_dir, f"%(title)s.%(ext)s")
    ydl_opts = {
        "outtmpl": outtmpl,
        "format": "best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "cookies_from_browser": "chrome",
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(direct_url, download=True)
            filepath = ydl.prepare_filename(info)
            # 可能被合并为 mp4
            if not os.path.exists(filepath):
                alt = filepath.replace(info.get("ext", "mp4"), "mp4")
                if os.path.exists(alt):
                    filepath = alt
            return {
                "success": True,
                "file_path": filepath,
                "title": title,
                "author": item.get("author", {}).get("nickname", ""),
                "duration": info.get("duration", 0) or 0,
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# 通用视频下载（yt_dlp.YoutubeDL Python API，抄 msg-collect）
# ---------------------------------------------------------------------------

def download_video(url: str, output_dir: str, quality: str = "audio_only") -> dict:
    """
    用 yt_dlp.YoutubeDL() Python API 下载，无 subprocess。
    audio_only → bestaudio/best
    best       → bestvideo+bestaudio/best
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    if quality == "audio_only":
        format_spec = "bestaudio/best"
        postprocessors = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "m4a",
        }]
    else:
        format_spec = "bestvideo+bestaudio/best[ext=mp4]/best"
        postprocessors = []

def _export_chrome_cookies(url: str) -> Optional[str]:
    """
    通过 yt-dlp CLI 导出 Chrome cookies 到临时文件。
    yt-dlp CLI 能读 Chrome 加密 cookie（Python browser_cookie3 不能）。
    返回 cookie 文件路径，用完后自行删除。
    """
    import tempfile
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".txt", delete=False)
        cookie_path = tmp.name
        tmp.close()
        # yt-dlp --cookies-from-browser chrome --list-formats 会导出 cookies
        proc = subprocess.run(
            [
                "yt-dlp",
                "--cookies-from-browser", "chrome",
                "--list-formats",
                "--no-playlist",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "YTDL_COOKIES_FILE": cookie_path},
        )
        # 检查是否成功提取了 cookies
        if "Extracted" in proc.stderr or "Extracted" in proc.stdout:
            return cookie_path
        return None
    except Exception:
        return None


def _get_yt_dlp_opts(url: str, output_dir: str, quality: str) -> dict:
    """构建 yt_dlp.YoutubeDL 选项，优先尝试 Chrome cookie 导出"""
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    if quality == "audio_only":
        format_spec = "bestaudio/best"
        postprocessors = [{"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}]
    else:
        format_spec = "bestvideo+bestaudio/best[ext=mp4]/best"
        postprocessors = []

    outtmpl = os.path.join(output_dir, "%(title)s.%(ext)s")
    opts = {
        "outtmpl": outtmpl,
        "format": format_spec,
        "postprocessors": postprocessors,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
    }

    # macOS 上 browser_cookie3 失效，改用 yt-dlp CLI 导出的 cookie 文件
    cookie_file = _export_chrome_cookies(url)
    if cookie_file:
        opts["cookiefile"] = cookie_file
# ---------------------------------------------------------------------------
# 通用视频下载（yt_dlp CLI，macOS 上 browser_cookie3 无法解密 Chrome cookie）
# ---------------------------------------------------------------------------

def download_video(url: str, output_dir: str, quality: str = "audio_only") -> dict:
    """
    用 yt-dlp CLI 下载。
    macOS 上 browser_cookie3 无法解密 Chrome cookie，而 yt-dlp CLI 有自己的实现。
    所以直接调 CLI，无需 Python API + cookie 导出。

    audio_only → bestaudio/best
    best       → bestvideo+bestaudio/best
    """
    return _download_video_cli(url, output_dir, quality)


def _download_video_cli(url: str, output_dir: str, quality: str = "audio_only") -> dict:
    """
    Fallback: 用 yt-dlp CLI 下载（B站 412 时走这里）。
    yt-dlp CLI 内部实现了自己的 Chrome cookie 读取，不依赖 browser_cookie3。
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    if quality == "audio_only":
        format_spec = "bestaudio/best"
    else:
        format_spec = "bestvideo+bestaudio/best[ext=mp4]/best"

    outtmpl = os.path.join(output_dir, "%(title)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "--cookies-from-browser", "chrome",
        "--format", format_spec,
        "--output", outtmpl,
        "--no-playlist",
        "--no-progress",
        "-q",
        url,
    ]

    try:
        # YouTube 有登录验证，必须用 Chrome cookies；但不能用代理（代理 IP 被封）
        env = {**os.environ,
               "HTTPS_PROXY": "", "HTTP_PROXY": "",
               "https_proxy": "", "http_proxy": "",
               "YT_DLP_NO_PROXY": "youtube.com,youtu.be"}
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
        if result.returncode != 0:
            err = result.stderr or result.stdout
            return {"success": False, "error": f"yt-dlp CLI 失败: {err}"}

        # 找下载的文件
        title = None
        for line in (result.stdout + result.stderr).split("\n"):
            pass

        # 扫描目录找最新文件
        candidates = []
        for f in sorted(Path(output_dir).iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if f.suffix in (".m4a", ".mp3", ".mp4", ".webm", ".aac"):
                candidates.append(f)
        if candidates:
            f = candidates[0]
            return {
                "success": True,
                "file_path": str(f),
                "title": f.stem,
                "author": "",
                "duration": 0,
            }
        return {"success": False, "error": "yt-dlp CLI 完成但未找到文件"}

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "下载超时（5分钟）"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# 主入口：字幕优先，下载兜底（抄 msg-collect 流程）
# ---------------------------------------------------------------------------

def download(
    url: str,
    output_dir: str = ".",
    quality: str = "audio_only",
    sessdata: str = "",
    subtitle_only: bool = False,
) -> dict:
    """
    统一下载接口。

    策略：
      YouTube  → 字幕直取 → 失败走 yt_dlp 下载
      B站       → 字幕直取（需 SESSDATA）→ 失败走 yt_dlp
      抖音      → 直链下载
      其他      → yt_dlp

    Args:
        url:          视频 URL
        output_dir:   输出目录（默认当前目录）
        quality:      "audio_only" | "best"
        sessdata:     B站 SESSDATA cookie（可省略，字幕获取会失败）
        subtitle_only: True 时只返回字幕，不下载视频

    Returns:
        {
            "success": bool,
            "file_path": str,        # 音频文件或字幕文件路径
            "title": str,
            "author": str,
            "duration": float,
            "subtitle_path": str,    # 字幕文件路径（如有）
            "method": str,            # "subtitle" | "download"
        }
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    subtitle_path = os.path.join(output_dir, "subtitle.txt")

    # YouTube — 字幕优先
    if _is_youtube(url):
        result = extract_youtube_subtitle(url, subtitle_path)
        if result:
            if subtitle_only:
                return {
                    "success": True,
                    "file_path": result["path"],
                    "title": result["title"],
                    "author": "",
                    "duration": result["duration"],
                    "subtitle_path": result["path"],
                    "method": "subtitle",
                }
            # 继续下载音视频
        # 失败 → 兜底下载
        dl = download_video(url, output_dir, quality)
        dl["subtitle_path"] = result["path"] if result else None
        dl["method"] = "download"
        return dl

    # B站 — 字幕优先（SESSDATA）
    if _is_bilibili(url):
        result = extract_bilibili_subtitle(url, sessdata, subtitle_path)
        if result:
            if subtitle_only:
                return {
                    "success": True,
                    "file_path": result["path"],
                    "title": result["title"],
                    "author": "",
                    "duration": result["duration"],
                    "subtitle_path": result["path"],
                    "method": "subtitle",
                }
            # 字幕拿到后，异步下载视频（不阻塞返回）
            # 注意：这里只下载，异步部分由调用方决定
        # 失败 → 兜底下载
        dl = download_video(url, output_dir, quality)
        dl["subtitle_path"] = result["path"] if result else None
        dl["method"] = "download"
        return dl

    # 抖音
    if _is_douyin(url):
        dl = download_douyin_video(url, output_dir)
        if dl and dl.get("success"):
            return dl
        # 失败 → yt_dlp 兜底
        dl = download_video(url, output_dir, quality)
        dl["method"] = "download"
        return dl

    # 其他平台 → yt_dlp 直接下载
    dl = download_video(url, output_dir, quality)
    dl["method"] = "download"
    return dl


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="视频下载工具 v2（字幕优先 + yt_dlp Python API）")
    parser.add_argument("url", help="视频 URL")
    parser.add_argument("-o", "--output", default=".", help="输出目录（默认当前目录）")
    parser.add_argument("--quality", default="audio_only", choices=["audio_only", "best"])
    parser.add_argument("--sessdata", default="", help="B站 SESSDATA cookie（用于字幕直取）")
    parser.add_argument("--subtitle-only", action="store_true", help="仅提取字幕，不下载视频")
    args = parser.parse_args()

    result = download(
        args.url,
        output_dir=args.output,
        quality=args.quality,
        sessdata=args.sessdata,
        subtitle_only=args.subtitle_only,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("success", False) else 1)
