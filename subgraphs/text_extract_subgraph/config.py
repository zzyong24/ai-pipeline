from __future__ import annotations
from dataclasses import dataclass

@dataclass
class TextExtractConfig:
    timeout: int = 60
    max_content_chars: int = 6000
