from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

@dataclass
class FilterConfig:
    timeout: int = 60
    min_approved: int = 1    # 最少通过几条（0=全部通过兜底）
    max_candidates: int = 20  # 最多处理多少条
