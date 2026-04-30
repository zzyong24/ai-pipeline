"""research_subgraph 节点实现。

核心改造：用 opencli 真实检索替换 LLM 瞎猜 URL。

改造前：让 LLM 凭记忆"推荐"视频 URL → 编造 BV 号 → 内容风马牛不相及
改造后：opencli bilibili search <topic> → 真实搜索结果 → 按热度过滤 → 真实 URL
"""
from __future__ import annotations
import json
import re
import subprocess
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional

from .state import ResearchState
from .config import ResearchConfig


# ─────────────────────────────────────────────────────────────────────────────
# opencli 调用层
# ─────────────────────────────────────────────────────────────────────────────

def _find_opencli(config: ResearchConfig) -> Optional[str]:
    """查找 opencli 可执行文件路径。"""
    if config.opencli_bin:
        return config.opencli_bin
    # 常见 nvm node22 路径
    candidates = [
        "/Users/zyongzhu/.nvm/versions/node/v22.22.2/bin/opencli",
        shutil.which("opencli"),
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return None


def _opencli_search(topic: str, config: ResearchConfig) -> List[Dict[str, Any]]:
    """
    用 opencli 在 B 站搜索真实视频，返回结果列表。

    返回格式：
        [{"rank": 1, "title": "...", "author": "...", "score": 1234, "url": "..."}, ...]
    """
    opencli = _find_opencli(config)
    if not opencli:
        raise RuntimeError(
            "opencli 未找到。请安装：npm install -g @jackwener/opencli\n"
            "并确保使用 Node >= 22。"
        )

    # Node 22 环境（opencli 要求）
    node22_bin = str(Path(opencli).parent)
    import os
    env = os.environ.copy()
    env["PATH"] = f"{node22_bin}:{env.get('PATH', '')}"

    cmd = [
        opencli, "bilibili", "search", topic,
        "--format", "json",
        "--limit", str(config.max_videos * 2),  # 多取一些，再过滤
    ]

    print(f"[research] opencli 搜索: {topic}")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=config.timeout,
        env=env,
    )

    if result.returncode != 0:
        raise RuntimeError(f"opencli 执行失败: {result.stderr[:200]}")

    try:
        items = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"opencli 输出解析失败: {e}\nstdout: {result.stdout[:200]}")

    return items if isinstance(items, list) else []


def _filter_and_rank(items: List[Dict], config: ResearchConfig) -> List[Dict]:
    """
    过滤 + 排序：
    1. 必须有 URL（opencli 有些结果 url 为空字符串）
    2. score 不低于 min_score
    3. 按 score 降序排，取前 max_videos 条
    """
    valid = [
        item for item in items
        if item.get("url", "").startswith("http")
        and item.get("score", 0) >= config.min_score
    ]
    valid.sort(key=lambda x: x.get("score", 0), reverse=True)
    return valid[:config.max_videos]


def _extract_urls(items: List[Dict]) -> List[str]:
    return [item["url"] for item in items if item.get("url", "").startswith("http")]


def _save_to_disk(topic: str, selected: list, urls: list, output_dir: Path) -> None:
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


# ─────────────────────────────────────────────────────────────────────────────
# Node 工厂
# ─────────────────────────────────────────────────────────────────────────────

def make_research_node(config: ResearchConfig):
    """工厂：注入 config 后返回真正的 node 函数。"""

    def research_node(state: ResearchState) -> Dict[str, Any]:
        topic = state.get("topic", "").strip()
        if not topic:
            return {"error": "topic 不能为空", "selected_videos": [], "video_urls": []}

        print(f"[research] 用 opencli 检索 '{topic}'（B站真实搜索）...")

        try:
            # 1. opencli 真实搜索
            raw_items = _opencli_search(topic, config)

            # 2. 过滤 + 排序
            selected = _filter_and_rank(raw_items, config)
            urls = _extract_urls(selected)

            print(f"[research] 完成：找到 {len(urls)} 个真实视频")
            for i, v in enumerate(selected, 1):
                print(f"  {i}. [{v.get('score', 0):>6}热度] {v.get('title', '')[:40]}  {v.get('url', '')}")

            # 3. 若无结果，报错
            if not urls:
                return {
                    "error": f"opencli 搜索 '{topic}' 无有效结果（可能需要检查 opencli 安装或 Cookie）",
                    "selected_videos": raw_items,
                    "video_urls": [],
                }

            if config.output_dir:
                _save_to_disk(topic, selected, urls, config.output_dir)

            return {
                "raw_llm_output": None,          # opencli 不需要 LLM，清空旧字段
                "selected_videos": selected,
                "video_urls": urls,
                "error": None,
            }

        except subprocess.TimeoutExpired:
            print(f"[research] opencli 超时（{config.timeout}s）")
            return {"error": f"opencli 搜索超时", "selected_videos": [], "video_urls": []}
        except Exception as e:
            print(f"[research] 失败: {e}")
            return {"error": str(e), "selected_videos": [], "video_urls": []}

    return research_node
