"""write_book_subgraph 可调参数。"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class WriteBookConfig:
    """书稿生成 SubGraph 配置。

    字段：
      - timeout_aggregate: 聚合 LLM 超时秒
      - timeout_write:     书稿 LLM 超时秒
      - min_chapters:      书稿期望最少章节数
      - min_words:         书稿期望最少字数
    """
    timeout_aggregate: int = 180
    timeout_write: int = 300
    min_chapters: int = 5
    min_words: int = 2000
