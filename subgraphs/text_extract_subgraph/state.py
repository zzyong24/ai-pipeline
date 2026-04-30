from __future__ import annotations
from typing import TypedDict, Optional, Any

class TextExtractState(TypedDict, total=False):
    source_type: str
    source_url: str
    title: str
    text_content: str
    author: str
    idx: int
    topic: str
    summary: Optional[str]
    error: Optional[str]
    _trace_span: Optional[Any]
