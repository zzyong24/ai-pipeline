"""transcribe_subgraph 可调参数。"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class TranscribeConfig:
    """转录 SubGraph 配置。

    字段：
      - timeout_download:     下载超时秒，默认 300
      - timeout_transcribe:   转录超时秒，默认 600（字幕优先后 Whisper 只跑无字幕视频，可适当延长）
      - timeout_summarize:    总结超时秒，默认 120
      - output_base:          输出根目录，每个任务在 output_base/task-{idx}/
      - tools_src:            工具源码目录（video_download/audio_transcribe/whisper_summarizer 的父目录）
      - opencli_bin:          opencli 可执行路径，默认 None（自动查找）
      - use_subtitle_first:   True=优先用 opencli 取字幕，字幕缺失才用 Whisper；默认 True
    """
    timeout_download: int = 300
    timeout_transcribe: int = 600    # 字幕优先后只剩无字幕视频，给够时间
    timeout_summarize: int = 120
    output_base: Optional[Path] = None
    tools_src: Optional[Path] = None
    opencli_bin: Optional[str] = None   # None 时自动查找
    use_subtitle_first: bool = True     # 优先用 opencli 取字幕
