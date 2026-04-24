#!/usr/bin/env python3
"""
n8n Execute Command pipeline wrapper
====================================

n8n Execute Command 通过 shell exec 执行命令字符串。
n8n 会在执行前展开 {{ $json.xxx }} 等表达式。

但 shell 会对字符串做 token 解析——含空格/特殊字符的路径/URL 会断裂。
正确做法：用 Python 接收 JSON stdin，不靠 shell 传参。

n8n Execute Command node 配置
------------------------------
Command 字段（两种模式）:

模式A - 参数在命令里（适用于简单值）:
    python3 /path/to/n8n_pipeline.py '{"action":"download","url":"{{ $json.url }}"}'

模式B - 纯命令，stdin 传 JSON（适用于含空格的复杂值）:
    python3 /path/to/n8n_pipeline.py
    (n8n 通过 Execute Command 的 "Parameterized" 模式或单独 JSON body 传 stdin)

推荐模式A，因为 n8n Execute Command node 不直接支持 stdin 注入。

输入 JSON 格式
--------------
{
  "action": "download" | "transcribe" | "summarize" | "full",
  "url": "https://...",
  "output_dir": "/tmp",
  "video_path": "/path/to/file.m4a",
  "srt_path": "/path/to/file.srt",
  "model": "base" | "tiny" | "small",
  "summary_prompt": "optional custom prompt"
}

输出 JSON（stdout）
------------------
{"success": true, "file_path": "...", "title": "...", ...}
{"success": false, "error": "..."}
"""

import sys
import json
import subprocess
import os
from pathlib import Path

# ===== 配置 =====
VENV_PY = "/Users/zyongzhu/Workbase/Msg-collect/.venv/bin/python"
TOOLS_SRC = Path("/Users/zyongzhu/Workbase/tools/src")


# ===== 内部工具 =====

def run_venv(script_path: Path, *args) -> subprocess.CompletedProcess:
    """用 tools venv 执行 Python 脚本"""
    cmd = [VENV_PY, str(script_path)] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=600)


def parse_json_output(stdout: str) -> dict:
    """解析工具输出的 JSON"""
    try:
        return json.loads(stdout.strip())
    except json.JSONDecodeError:
        return {"raw": stdout, "error": "JSON解析失败"}


# ===== Actions =====

def action_download(url: str, output_dir: str = "/tmp") -> dict:
    """下载视频/音频（ subprocess 调用 yt-dlp CLI）"""
    script = TOOLS_SRC / "video_download" / "downloader.py"
    result = run_venv(script, url, "-o", output_dir, "--quality", "audio_only")
    
    if result.returncode != 0:
        return {"success": False, "step": "download", "error": result.stderr or result.stdout}
    
    data = parse_json_output(result.stdout)
    if not data.get("success"):
        return {"success": False, "step": "download", "error": data.get("error", "未知错误")}
    
    return {
        "success": True,
        "step": "download",
        "file_path": data["file_path"],
        "title": data.get("title", ""),
        "author": data.get("author", ""),
        "duration": data.get("duration", 0),
    }


def action_transcribe(video_path: str, model: str = "base", output_dir: str = None) -> dict:
    """转录视频/音频 → SRT 字幕文件"""
    if output_dir is None:
        output_dir = str(Path(video_path).parent)
    
    script = TOOLS_SRC / "audio_transcribe" / "cli.py"
    result = run_venv(script, video_path, "-o", output_dir, "--model", model)
    
    if result.returncode != 0:
        return {"success": False, "step": "transcribe", "error": result.stderr or result.stdout}
    
    # 找生成的 SRT 文件
    video_name = Path(video_path).stem
    srt_candidates = list(Path(output_dir).glob(f"{video_name}.srt"))
    srt_path = str(srt_candidates[0]) if srt_candidates else ""
    
    return {
        "success": True,
        "step": "transcribe",
        "srt_path": srt_path,
        "video_path": video_path,
        "model": model,
    }


def action_summarize(srt_path: str, summary_prompt: str = None) -> dict:
    """用 MiniMax summarizer 分析 SRT，生成摘要"""
    script = TOOLS_SRC / "whisper_summarizer" / "summarizer.py"
    
    args = [srt_path]
    if summary_prompt:
        # prompt 通过文件传入（避免 shell 转义问题）
        prompt_file = Path(srt_path).with_suffix(".prompt.txt")
        prompt_file.write_text(summary_prompt, encoding="utf-8")
        args.extend(["--prompt-file", str(prompt_file)])
    
    result = run_venv(script, *args)
    
    if result.returncode != 0:
        return {"success": False, "step": "summarize", "error": result.stderr or result.stdout}
    
    summary_data = parse_json_output(result.stdout)
    summary_data["step"] = "summarize"
    summary_data["success"] = True
    return summary_data


def action_full(url: str, output_dir: str = "/tmp", model: str = "base") -> dict:
    """一条龙完整流程：下载 → 转录 → 总结"""
    
    # Step 1: 下载
    dl = action_download(url, output_dir)
    if not dl["success"]:
        return dl
    video_path = dl["file_path"]
    
    # Step 2: 转录
    tc = action_transcribe(video_path, model=model)
    if not tc["success"]:
        return tc
    srt_path = tc["srt_path"]
    
    # Step 3: 总结
    sm = action_summarize(srt_path)
    if not sm["success"]:
        return sm
    
    return {
        "success": True,
        "step": "full",
        "url": url,
        "video_path": video_path,
        "srt_path": srt_path,
        "title": dl.get("title", ""),
        "author": dl.get("author", ""),
        "duration": dl.get("duration", 0),
        "summary": sm.get("summary", sm.get("raw", {})),
    }


# ===== 主入口 =====

def main():
    input_data = {}
    
    # 方式1: 从 sys.argv[1] 读取 JSON（n8n 命令参数）
    if len(sys.argv) > 1:
        try:
            input_data = json.loads(sys.argv[1])
        except json.JSONDecodeError as e:
            print(json.dumps({"success": False, "error": f"JSON参数解析失败: {e}"}))
            sys.exit(1)
    
    # 方式2: 从 stdin 读取 JSON（备用）
    elif not sys.stdin.isatty():
        raw = sys.stdin.read().strip()
        if raw:
            try:
                input_data = json.loads(raw)
            except json.JSONDecodeError as e:
                print(json.dumps({"success": False, "error": f"stdin JSON解析失败: {e}"}))
                sys.exit(1)
    
    else:
        print(json.dumps({"success": False, "error": "没有收到输入参数，请通过命令行参数传递 JSON"}))
        sys.exit(1)
    
    action = input_data.get("action", "")
    
    try:
        if action == "download":
            result = action_download(
                url=input_data["url"],
                output_dir=input_data.get("output_dir", "/tmp"),
            )
        elif action == "transcribe":
            result = action_transcribe(
                video_path=input_data["video_path"],
                model=input_data.get("model", "base"),
                output_dir=input_data.get("output_dir"),
            )
        elif action == "summarize":
            result = action_summarize(
                srt_path=input_data["srt_path"],
                summary_prompt=input_data.get("summary_prompt"),
            )
        elif action == "full":
            result = action_full(
                url=input_data["url"],
                output_dir=input_data.get("output_dir", "/tmp"),
                model=input_data.get("model", "base"),
            )
        else:
            result = {"success": False, "error": f"未知 action: {action}"}
    except Exception as e:
        result = {"success": False, "error": f"执行异常: {e}"}
    
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("success", False) else 1)


if __name__ == "__main__":
    main()
