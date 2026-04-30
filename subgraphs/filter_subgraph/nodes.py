"""filter_subgraph 节点实现。
AI 自动相关性审核：一次 LLM 调用批量判断候选条目与 topic 的相关性。
"""
from __future__ import annotations
import json
import re
from typing import Dict, Any
from ..shared.llm import llm_minimax
from ..shared.timeout import with_timeout
from .state import FilterState
from .config import FilterConfig


def _parse_filter_result(text: str) -> list:
    """提取 LLM 返回的 JSON 列表，兼容 markdown 代码块。"""
    # 去掉 ```json ... ``` 包装
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    # 找第一个 [ 到最后一个 ]
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        return json.loads(text[start:end+1])
    except Exception:
        return []


def make_filter_node(config: FilterConfig):
    def filter_node(state: FilterState) -> Dict[str, Any]:
        topic = state.get("topic", "")
        candidates = state.get("candidates", [])[:config.max_candidates]
        trace_span = state.get("_trace_span")

        print(f"[filter] 开始相关性过滤，topic='{topic}'，候选 {len(candidates)} 条...")

        if not candidates:
            return {"approved_items": [], "rejected_items": [], "filter_log": []}

        # 构建候选摘要（避免推文全文太长）
        items_for_prompt = []
        for item in candidates:
            snippet = (item.get("text_content") or item.get("title") or "")[:200]
            items_for_prompt.append({
                "url": item.get("url", ""),
                "title": item.get("title", ""),
                "source_type": item.get("source_type", ""),
                "author": item.get("author", ""),
                "snippet": snippet,
            })

        prompt = f"""你是一个信息质量过滤器。主题：「{topic}」

以下是来自不同平台的候选内容，请判断每条内容与主题的相关性。

候选内容：
{json.dumps(items_for_prompt, ensure_ascii=False, indent=2)}

输出 JSON 数组，每条包含：
- url: 原 URL
- relevant: true/false
- reason: 一句话说明原因（中文）

过滤标准：
✅ 相关：直接讨论该技术/趋势/问题；有实质性分析观点；来自可信作者的一手信息
❌ 不相关：纯营销软文；入门/培训教程；招聘广告；与主题仅有关键词重叠但内容无关

只输出 JSON 数组，不要其他文字。"""

        try:
            result_text = llm_minimax(
                prompt, timeout=max(10, config.timeout - 10),
                trace_span=trace_span, generation_name="filter/relevance_check",
            )
            filter_results = _parse_filter_result(result_text)

            # 建立 url -> {relevant, reason} 映射
            url_map = {r.get("url", ""): r for r in filter_results if isinstance(r, dict)}

            approved, rejected, log = [], [], []
            for item in candidates:
                url = item.get("url", "")
                decision = url_map.get(url, {})
                relevant = decision.get("relevant", True)  # 未匹配到默认通过
                reason = decision.get("reason", "未匹配，默认通过")
                log.append({"url": url, "title": item.get("title", ""), "relevant": relevant, "reason": reason})
                if relevant:
                    approved.append(item)
                else:
                    rejected.append(item)

            print(f"[filter] 完成：通过 {len(approved)} 条，拒绝 {len(rejected)} 条")
            for entry in log:
                status = "✅" if entry["relevant"] else "❌"
                print(f"  {status} {entry['title'][:40]} — {entry['reason']}")

            # 兜底：如果全部被拒，保留所有（避免空输出）
            if not approved and config.min_approved > 0:
                print(f"[filter] ⚠️ 全部被拒，兜底保留所有 {len(candidates)} 条")
                approved = candidates
                rejected = []

            return {"approved_items": approved, "rejected_items": rejected, "filter_log": log, "error": None}

        except Exception as e:
            print(f"[filter] 失败: {e}，兜底保留所有候选")
            return {"approved_items": candidates, "rejected_items": [], "filter_log": [], "error": str(e)}

    return with_timeout(config.timeout)(filter_node)
