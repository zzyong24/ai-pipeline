"""音频转字幕工具 — 单一职责：本地音频文件 → SRT/VTT/TXT 字幕

依赖 msg-collect venv 中的 faster-whisper。
运行时：~/Workbase/Msg-collect/.venv/bin/python -m audio_transcribe <audio_path> -o OUTPUT_DIR
"""

import os
import sys
import re
import json
import argparse
from pathlib import Path
from datetime import timedelta

# Pipeline venv 的 faster-whisper 已可用，不需要额外注入

from faster_whisper import WhisperModel


def _format_timestamp(seconds: float, fmt: str = "srt") -> str:
    """秒 → SRT/VTT 时间戳"""
    td = timedelta(seconds=seconds)
    h = td.seconds // 3600
    m = (td.seconds % 3600) // 60
    s = td.seconds % 60
    ms = td.microseconds // 1000
    if fmt == "srt":
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _seconds_to_vtt_time(seconds: float) -> str:
    return _format_timestamp(seconds, "vtt")


class AudioTranscriber:
    """最小粒度转录工具：本地音频 → 字幕文件"""

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None

    def _model_instance(self):
        if self._model is None:
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
        return self._model

    def transcribe(self, audio_path: str, output_dir: str = ".") -> dict:
        """
        转录本地音频文件，输出 SRT/VTT/TXT。

        Returns:
            {
                "txt_path": str,
                "srt_path": str,
                "vtt_path": str,
                "duration": float,       # 秒
                "transcription_time": float,
                "language": str,
            }
        """
        audio_path = Path(audio_path).resolve()
        if not audio_path.exists():
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        model = self._model_instance()

        # 转录（word_timestamps=True 用于精确时间轴）
        segments, info = model.transcribe(
            str(audio_path),
            language="zh",
            word_timestamps=True,
        )

        # 收集所有分段
        segment_list = []
        for seg in segments:
            segment_list.append(
                {
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text.strip(),
                }
            )

        # 写入 TXT（纯文本）
        txt_path = output_dir / f"{audio_path.stem}.txt"
        with open(txt_path, "w", encoding="utf-8") as f:
            for seg in segment_list:
                f.write(seg["text"] + "\n")

        # 写入 SRT
        srt_path = output_dir / f"{audio_path.stem}.srt"
        with open(srt_path, "w", encoding="utf-8") as f:
            for i, seg in enumerate(segment_list, 1):
                start_ts = _format_timestamp(seg["start"], "srt")
                end_ts = _format_timestamp(seg["end"], "srt")
                f.write(f"{i}\n")
                f.write(f"{start_ts} --> {end_ts}\n")
                f.write(f"{seg['text']}\n\n")

        # 写入 VTT
        vtt_path = output_dir / f"{audio_path.stem}.vtt"
        with open(vtt_path, "w", encoding="utf-8") as f:
            f.write("WEBVTT\n\n")
            for i, seg in enumerate(segment_list, 1):
                start_ts = _seconds_to_vtt_time(seg["start"])
                end_ts = _seconds_to_vtt_time(seg["end"])
                f.write(f"{i}\n")
                f.write(f"{start_ts} --> {end_ts}\n")
                f.write(f"{seg['text']}\n\n")

        # 统计信息（从 info 提取）
        audio_duration = info.duration or 0.0
        language = info.language or "zh"

        # 总转录时间（不含模型加载）
        transcription_time = (
            segment_list[-1]["end"] if segment_list else 0.0
        )

        return {
            "txt_path": str(txt_path),
            "srt_path": str(srt_path),
            "vtt_path": str(vtt_path),
            "duration": round(audio_duration, 2),
            "language": language,
            "transcription_time": round(transcription_time, 2),
            "segments_count": len(segment_list),
        }


def transcribe(audio_path: str, output_dir: str = ".") -> dict:
    """CLI 封装"""
    return AudioTranscriber().transcribe(audio_path, output_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="音频转字幕工具（faster-whisper）")
    parser.add_argument("audio_path", help="本地音频文件路径")
    parser.add_argument("-o", "--output", default=".", help="输出目录（默认当前目录）")
    parser.add_argument(
        "--model",
        default="base",
        choices=["tiny", "base", "small", "medium"],
        help="Whisper 模型大小（默认 base）",
    )
    args = parser.parse_args()

    result = transcribe(args.audio_path, args.output)
    print(json.dumps(result, ensure_ascii=False))
