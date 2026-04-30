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
# 多源搜索层
# ─────────────────────────────────────────────────────────────────────────────

def _load_builders(config: ResearchConfig) -> List[str]:
    """从 builders.json 或 config.builders 加载 handle 列表。"""
    if config.builders:
        return config.builders
    if config.builders_config_path and Path(config.builders_config_path).exists():
        import json as _json
        data = _json.loads(Path(config.builders_config_path).read_text(encoding="utf-8"))
        return [b["handle"] for b in data.get("builders", []) if b.get("handle")]
    return []


def _run_opencli_cmd(cmd: list, config: ResearchConfig, timeout: int = None) -> list:
    """通用 opencli 调用，失败返回空列表（静默跳过）。"""
    import os as _os
    opencli = _find_opencli(config)
    if not opencli:
        return []
    node22_bin = str(Path(opencli).parent)
    env = _os.environ.copy()
    env["PATH"] = f"{node22_bin}:{env.get('PATH', '')}"
    full_cmd = [opencli] + cmd
    try:
        result = subprocess.run(
            full_cmd, capture_output=True, text=True,
            timeout=timeout or config.timeout, env=env,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        items = json.loads(result.stdout)
        return items if isinstance(items, list) else []
    except Exception as e:
        print(f"[research] opencli 调用失败（静默跳过）: {e}")
        return []


def _normalize_item(item: dict, source_type: str) -> dict:
    """把各平台原始条目统一为标准格式。"""
    return {
        "source_type": source_type,
        "title": item.get("title") or item.get("text", "")[:80],
        "author": item.get("author", ""),
        "url": item.get("url", ""),
        "score": item.get("score") or item.get("likes") or item.get("views") or 0,
        "text_content": item.get("text") or item.get("content") or "",
    }


def _search_hackernews(topic: str, config: ResearchConfig) -> List[Dict]:
    print(f"[research] HackerNews 搜索: {topic}")
    items = _run_opencli_cmd(
        ["hackernews", "search", topic, "--format", "json", "--limit", str(config.max_videos * 2)],
        config,
    )
    return [_normalize_item(i, "hackernews") for i in items if i.get("url")]


def _search_zhihu(topic: str, config: ResearchConfig) -> List[Dict]:
    print(f"[research] 知乎搜索: {topic}")
    items = _run_opencli_cmd(
        ["zhihu", "search", topic, "--format", "json", "--limit", str(config.max_videos * 2)],
        config,
    )
    return [_normalize_item(i, "zhihu") for i in items if i.get("url")]


def _search_twitter(topic: str, config: ResearchConfig) -> List[Dict]:
    print(f"[research] Twitter 搜索: {topic}（失败静默跳过）")
    items = _run_opencli_cmd(
        ["twitter", "search", topic, "--format", "json", "--limit", str(config.max_videos * 2)],
        config, timeout=20,
    )
    return [_normalize_item(i, "twitter") for i in items if i.get("url")]


def _fetch_builder_tweets(config: ResearchConfig) -> List[Dict]:
    """批量抓取 builder 推文，合并去重。"""
    handles = _load_builders(config)
    if not handles:
        return []
    print(f"[research] 抓取 {len(handles)} 个 builder 推文: {handles}")
    all_items = []
    seen_urls = set()
    for handle in handles:
        items = _run_opencli_cmd(
            ["twitter", "tweets", handle, "--format", "json", "--limit", "10"],
            config, timeout=20,
        )
        for item in items:
            normalized = _normalize_item(item, "twitter")
            if normalized["url"] and normalized["url"] not in seen_urls:
                normalized["author"] = handle  # 确保 author 是 handle
                seen_urls.add(normalized["url"])
                all_items.append(normalized)
    print(f"[research] Builder 推文：共 {len(all_items)} 条")
    return all_items


# ─────────────────────────────────────────────────────────────────────────────
# Node 工厂
# ─────────────────────────────────────────────────────────────────────────────

def make_research_node(config: ResearchConfig):
    """工厂：注入 config 后返回真正的 node 函数。"""

    def research_node(state: ResearchState) -> Dict[str, Any]:
        topic = state.get("topic", "").strip()
        if not topic:
            return {"error": "topic 不能为空", "selected_videos": [], "video_urls": [], "source_items": []}

        sources = state.get("sources") or config.sources or ["bilibili"]
        print(f"[research] 用 opencli 检索 '{topic}'（sources={sources}）...")

        try:
            all_items = []

            for src in sources:
                if src == "bilibili":
                    raw = _opencli_search(topic, config)
                    filtered = _filter_and_rank(raw, config)
                    for item in filtered:
                        all_items.append(_normalize_item(item, "bilibili"))
                elif src == "hackernews":
                    all_items.extend(_search_hackernews(topic, config))
                elif src == "zhihu":
                    all_items.extend(_search_zhihu(topic, config))
                elif src == "twitter":
                    all_items.extend(_search_twitter(topic, config))
                elif src == "twitter_builders":
                    all_items.extend(_fetch_builder_tweets(config))

            # 去重（按 url）
            seen_urls = set()
            deduped = []
            for item in all_items:
                if item["url"] and item["url"] not in seen_urls:
                    seen_urls.add(item["url"])
                    deduped.append(item)

            # 视频 URL（向后兼容）
            video_items = [i for i in deduped if i["source_type"] == "bilibili"]
            video_urls = [i["url"] for i in video_items]

            print(f"[research] 完成：{len(deduped)} 条（bilibili={len(video_items)}, 其他={len(deduped)-len(video_items)}）")
            for item in deduped:
                print(f"  [{item['source_type']}] {item['title'][:40]}  {item['url'][:60]}")

            if not deduped:
                return {"error": f"所有来源搜索 '{topic}' 均无结果", "selected_videos": [], "video_urls": [], "source_items": []}

            if config.output_dir:
                _save_to_disk(topic, deduped, video_urls, config.output_dir)

            return {
                "raw_llm_output": None,
                "selected_videos": video_items,   # 向后兼容
                "video_urls": video_urls,          # 向后兼容
                "source_items": deduped,           # 新字段：所有来源
                "error": None,
            }
        except subprocess.TimeoutExpired:
            print(f"[research] 超时（{config.timeout}s）")
            return {"error": "搜索超时", "selected_videos": [], "video_urls": [], "source_items": []}
        except Exception as e:
            print(f"[research] 失败: {e}")
            return {"error": str(e), "selected_videos": [], "video_urls": [], "source_items": []}

    return research_node
