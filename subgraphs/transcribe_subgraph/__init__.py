"""transcribe_subgraph — 视频下载 + 转录 + 总结 三步合并 SubGraph

输入单个视频 URL 和任务索引，输出结构化总结。

暴露：
    - TranscribeState: State 定义
    - build_transcribe_subgraph: 构造函数
"""
from .state import TranscribeState
from .graph import build_transcribe_subgraph

__all__ = ["TranscribeState", "build_transcribe_subgraph"]
