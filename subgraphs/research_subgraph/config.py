"""research_subgraph 可调参数。"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ResearchConfig:
    """研究 SubGraph 配置。

    字段：
      - timeout:      LLM 调用超时秒数，默认 120
      - output_dir:   研究结果保存目录，默认 None 表示不保存到磁盘
      - min_videos:   至少希望 LLM 给出的视频数，默认 3
      - max_videos:   最多希望 LLM 给出的视频数，默认 5
    """
    timeout: int = 120
    output_dir: Optional[Path] = None
    min_videos: int = 3
    max_videos: int = 5
