"""write_book_subgraph — 多视频摘要聚合 + 书稿生成 SubGraph

输入多个视频的摘要，输出结构完整的电子书稿。

内部两步：
  aggregate: 摘要列表 → 综合报告
  write:     综合报告 → 完整书稿

暴露：
    - WriteBookState: State 定义
    - build_write_book_subgraph: 构造函数
"""
from .state import WriteBookState
from .graph import build_write_book_subgraph

__all__ = ["WriteBookState", "build_write_book_subgraph"]
