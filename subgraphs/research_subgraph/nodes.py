"""research_subgraph 节点实现。

所有 node 是"纯函数"理想态：
  - 只读 State
  - 调工具函数
  - 返回部分 State 更新（dict）
"""
from __future__ import annotations
import re
import json
from pathlib import Path
from typing import Dict, Any

from ..shared.llm import llm_minimax
from ..shared.timeout import with_timeout
from .state import ResearchState
from .config import ResearchConfig


def _build_search_prompt(topic: str, min_v: int, max_v: int) -> str:
    """构造搜索 prompt（纯函数）。"""
    return f"""你是一个视频推荐专家。为主题「{topic}」推荐 {min_v}-{max_v} 个最相关的 B站（bilibili.com）或 YouTube（youtube.com）视频。

要求：
- 只推荐真实存在的视频链接
- 优先选择播放量高、内容精准的视频
- B站链接格式如：https://www.bilibili.com/video/BV1xx411xx/
- YouTube 链接格式如：https://www.youtube.com/watch?v=xxxxxx

返回纯 JSON 数组：
[
  {{"title": "视频标题", "url": "视频链接", "platform": "bilibili/youtube", "note": "一句话推荐理由"}}
]

只返回 JSON，不要其他内容。"""


def _parse_llm_output(raw: str) -> list:
    """从 LLM 返回里提取 JSON 数组（纯函数）。"""
    json_match = re.search(r"\[[\s\S]*\]", raw)
    if not json_match:
        return []
    try:
        return json.loads(json_match.group())
    except Exception:
        return []


def _extract_valid_urls(selected: list) -> list[str]:
    """从 selected 中提取合法视频 URL（纯函数）。"""
    urls = []
    for v in selected:
        url = v.get("url", "") if isinstance(v, dict) else str(v)
        if url and ("bilibili.com" in url or "youtube.com" in url):
            urls.append(url)
    return urls


def _save_to_disk(topic: str, selected: list, urls: list[str], output_dir: Path) -> None:
    """保存研究结果到磁盘（纯 IO）。"""
    safe_topic = "".join(c if c.isalnum() or c in " -_" else "_" for c in topic)[:30]
    target = output_dir / safe_topic
    target.mkdir(parents=True, exist_ok=True)
    (target / "research_results.json").write_text(
        json.dumps(
            {"topic": topic, "selected_videos": selected, "video_urls": urls},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )


def make_research_node(config: ResearchConfig):
    """工厂：注入 config 后返回真正的 node 函数。"""

    @with_timeout(config.timeout)
    def research_node(state: ResearchState) -> Dict[str, Any]:
        topic = state.get("topic", "").strip()
        if not topic:
            return {"error": "topic 不能为空", "selected_videos": [], "video_urls": []}

        print(f"[research] 搜集 '{topic}' 相关视频...")

        try:
            prompt = _build_search_prompt(topic, config.min_videos, config.max_videos)
            raw = llm_minimax(prompt, timeout=max(10, config.timeout - 10))
            selected = _parse_llm_output(raw)
            urls = _extract_valid_urls(selected)

            print(f"[research] 完成：找到 {len(urls)} 个视频")

            if config.output_dir:
                _save_to_disk(topic, selected, urls, config.output_dir)

            return {
                "raw_llm_output": raw,
                "selected_videos": selected,
                "video_urls": urls,
                "error": None,
            }

        except TimeoutError as e:
            print(f"[research] 超时: {e}")
            return {"error": f"research timeout: {e}", "selected_videos": [], "video_urls": []}
        except Exception as e:
            print(f"[research] 失败: {e}")
            return {"error": f"research failed: {e}", "selected_videos": [], "video_urls": []}

    return research_node
