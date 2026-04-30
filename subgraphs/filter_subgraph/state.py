from __future__ import annotations
from typing import TypedDict, List, Dict, Any, Optional

class FilterState(TypedDict, total=False):
    topic: str
    candidates: List[Dict[str, Any]]    # 输入
    approved_items: List[Dict[str, Any]] # 输出
    rejected_items: List[Dict[str, Any]] # 输出
    filter_log: List[Dict[str, Any]]     # 每条的判断 reason
    error: Optional[str]
    _trace_span: Optional[Any]
