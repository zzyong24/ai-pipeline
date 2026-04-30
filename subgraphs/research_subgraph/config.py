"""research_subgraph 可调参数。"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List


@dataclass
class ResearchConfig:
    """研究 SubGraph 配置。

    字段：
      - timeout:        命令超时秒数，默认 30
      - output_dir:     研究结果保存目录，默认 None 表示不保存到磁盘
      - min_videos:     至少需要的视频数，默认 3
      - max_videos:     最多检索的视频数，默认 10
      - source:         内容来源，默认 "bilibili"，支持 "bilibili"
      - opencli_bin:    opencli 可执行文件路径，默认 None（自动查找）
      - min_score:      最低播放量/热度过滤阈值，默认 0（不过滤）
      - sources:        多信息源列表，默认 ["bilibili"]
      - builders:       Twitter builder handle 列表
      - builders_config_path: builders.json 文件路径
    """
    timeout: int = 30
    output_dir: Optional[Path] = None
    min_videos: int = 3
    max_videos: int = 10
    source: str = "bilibili"
    opencli_bin: Optional[str] = None  # None 时自动查找
    min_score: int = 0                 # 过滤低热度视频
    sources: List[str] = field(default_factory=lambda: ["bilibili"])
    builders: List[str] = field(default_factory=list)
    builders_config_path: Optional[Path] = None
