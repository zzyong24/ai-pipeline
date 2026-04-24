"""B站视频信息获取 — 输入 URL，返回是否多P及分P列表"""
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlparse
from typing import Optional

_MSGVENV = "/Users/zyongzhu/Workbase/Msg-collect/.venv/lib/python3.12/site-packages"
if Path(_MSGVENV).exists() and _MSGVENV not in sys.path:
    sys.path.insert(0, _MSGVENV)

from bilibili_api import video


def _is_bilibili_url(url: str) -> bool:
    try:
        netloc = urlparse(url).netloc.lower()
    except Exception:
        return False
    return "bilibili.com" in netloc or "b23.tv" in netloc


def _resolve_short_url(url: str) -> str:
    """跟随 b23.tv 短链，获取真实 URL"""
    if "b23.tv" not in url:
        return url
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=15) as resp:
            return resp.geturl()
    except Exception:
        return url


def _extract_bvid(url: str) -> str:
    """从 URL 提取 BV 号"""
    url = _resolve_short_url(url)
    match = re.search(r"/video/(BV[0-9A-Za-z]+)", url)
    if match:
        return match.group(1)
    fallback = re.search(r"(BV[0-9A-Za-z]+)", url)
    if fallback:
        return fallback.group(1)
    raise ValueError(f"无法从链接中提取 BV 号: {url}")


import asyncio

def fetch_video_info(url: str) -> dict:
    """
    获取 B 站视频信息。

    Returns:
        {
            "is_multi_part": bool,
            "title": str,
            "bvid": str,
            "duration": int,  # 秒
            "parts": [  # 仅 is_multi_part=True 时
                {"index": int, "cid": int, "title": str, "duration": int},
            ],
        }
    """
    return asyncio.run(_fetch_video_info(url))


async def _fetch_video_info(url: str) -> dict:
    if not _is_bilibili_url(url):
        raise ValueError(f"不是有效的 B 站视频链接: {url}")

    bvid = _extract_bvid(url)
    v = video.Video(bvid=bvid)
    info = await v.get_info()

    title = str(info.get("title") or "")
    duration = int(info.get("duration") or 0)
    pages = info.get("pages") or []

    if isinstance(pages, list) and len(pages) > 1:
        parts = [
            {
                "index": int(p.get("page", 0)) - 1,  # 0-based
                "cid": int(p.get("cid", 0)),
                "title": str(p.get("part") or f"第{int(p.get('page',0))}P"),
                "duration": int(p.get("duration") or 0),
            }
            for p in pages
            if isinstance(p, dict)
        ]
        return {
            "is_multi_part": True,
            "title": title,
            "bvid": bvid,
            "duration": duration,
            "parts": parts,
        }
    else:
        return {
            "is_multi_part": False,
            "title": title,
            "bvid": bvid,
            "duration": duration,
            "parts": None,
        }
