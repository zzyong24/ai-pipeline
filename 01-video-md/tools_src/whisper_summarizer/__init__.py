"""字幕总结工具 — 单一职责：SRT/TXT → 结构化总结（直调 MiniMax API）"""

from .summarizer import summarize, WhisperSummarizer

__all__ = ["summarize", "WhisperSummarizer"]
