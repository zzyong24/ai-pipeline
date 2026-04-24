"""音频转字幕工具 — 单一职责：本地音频 → SRT/VTT/TXT（faster-whisper）"""

from .transcriber import transcribe, AudioTranscriber

__all__ = ["transcribe", "AudioTranscriber"]
