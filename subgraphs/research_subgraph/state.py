"""research_subgraph State 定义。

分三层：
  ① 输入字段：父 Graph 传入
  ② 中间字段：节点之间传递
  ③ 输出字段：父 Graph 要的

规范：vault/space/crafted/study/langgraph-subgraph/subgraph-design-spec.md
"""
from __future__ import annotations
from typing import TypedDict, List, Dict, Any, Optional


class ResearchState(TypedDict, total=False):
    # ───────────── ① 输入字段 ─────────────
    topic: str
    """研究主题（必填）
    - 含义：用户想要研究的话题
    - 类型：str
    - 约束：非空字符串
    """

    # ───────────── ② 中间字段 ─────────────
    raw_llm_output: Optional[str]
    """LLM 原始输出
    - 含义：LLM 返回的原始 JSON 字符串
    - 类型：Optional[str]
    - 默认值：None
    """

    # ───────────── ③ 输出字段 ─────────────
    selected_videos: List[Dict[str, Any]]
    """选中的视频元数据列表
    - 含义：每条记录包含 title/url/platform/note
    - 类型：List[Dict[str, Any]]
    - 默认值：[]
    """

    video_urls: List[str]
    """候选视频 URL 列表（清洗后）
    - 含义：过滤掉非 bilibili/youtube 的 URL 后的列表
    - 类型：List[str]
    - 默认值：[]
    """

    error: Optional[str]
    """错误信息（如有）
    - 含义：research 失败时的 reason，None 表示无错误
    - 类型：Optional[str]
    - 默认值：None
    """

    # ───────────── ④ 可观测（透传） ─────────────
    _trace_span: Optional[Any]
    """Langfuse trace/span 对象（透传用，不参与业务）
    - 含义：由主 Graph 创建并透传，SubGraph 用于埋点
    - 类型：Optional[Any]
    - 默认值：None
    """
