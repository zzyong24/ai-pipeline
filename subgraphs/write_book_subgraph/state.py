"""write_book_subgraph State 定义。

分三层：
  ① 输入字段：父 Graph 传入
  ② 中间字段：aggregate → write 传递
  ③ 输出字段：父 Graph 要的
"""
from __future__ import annotations
from typing import TypedDict, List, Dict, Any, Optional


class WriteBookState(TypedDict, total=False):
    # ───────────── ① 输入字段 ─────────────
    topic: str
    """书稿主题（必填）
    - 含义：最终书的主题
    - 类型：str
    """

    summaries: List[Dict[str, Any]]
    """视频摘要列表（必填）
    - 含义：每条包含 video/title/summary
    - 类型：List[Dict]
    - 约束：非空；为空时会生成占位书稿
    """

    # ───────────── ② 中间字段 ─────────────
    integrated_report: Optional[str]
    """综合报告（aggregate 步骤输出）
    - 含义：多视频摘要整合后的报告
    - 类型：Optional[str]
    """

    # ───────────── ③ 输出字段 ─────────────
    book: Optional[str]
    """最终书稿（write 步骤输出）
    - 含义：结构完整的电子书正文（不含 H1 标题）
    - 类型：Optional[str]
    """

    error: Optional[str]
    """错误信息（如有）"""

    # ───────────── ④ 可观测（透传） ─────────────
    _trace_span: Optional[Any]
    """Langfuse trace/span 对象（透传用，不参与业务）
    - 含义：由主 Graph 创建并透传，SubGraph 用于埋点
    - 类型：Optional[Any]
    - 默认值：None
    """
