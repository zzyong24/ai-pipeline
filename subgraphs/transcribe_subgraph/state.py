"""transcribe_subgraph State 定义。

分三层：
  ① 输入字段：父 Graph 传入
  ② 中间字段：三个节点之间传递
  ③ 输出字段：父 Graph 要的
"""
from __future__ import annotations
from typing import TypedDict, Optional


class TranscribeState(TypedDict, total=False):
    # ───────────── ① 输入字段 ─────────────
    video_url: str
    """视频 URL
    - 含义：要处理的视频链接（B 站或 YouTube）
    - 类型：str
    - 约束：必须包含 bilibili.com 或 youtube.com
    """

    task_idx: int
    """任务索引
    - 含义：用于输出目录隔离，避免并行写入冲突
    - 类型：int
    - 约束：>= 0
    """

    topic: str
    """主题（可选，用于上下文）
    - 含义：父 Graph 的整体主题
    - 类型：str
    - 默认值：''
    """

    # ───────────── ② 中间字段 ─────────────
    file_path: Optional[str]
    """下载得到的文件路径"""

    subtitle_path: Optional[str]
    """字幕直取路径（若有）"""

    srt_path: Optional[str]
    """转录/字幕后的 SRT 文件路径"""

    download_method: Optional[str]
    """下载方法：download / subtitle"""

    title: Optional[str]
    """视频标题"""

    duration: Optional[int]
    """视频时长（秒）"""

    # ───────────── ③ 输出字段 ─────────────
    summary: Optional[str]
    """最终总结文本
    - 含义：whisper_summarizer 输出的结构化摘要
    - 类型：Optional[str]
    - 默认值：None
    """

    success: bool
    """是否成功
    - 含义：True 表示三步全通过，False 表示任一步失败
    - 类型：bool
    - 默认值：False
    """

    error: Optional[str]
    """错误信息
    - 含义：失败时的 reason，None 表示成功
    - 类型：Optional[str]
    - 默认值：None
    """
