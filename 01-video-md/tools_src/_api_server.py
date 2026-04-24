#!/usr/bin/env python3
"""
tools HTTP API server — 把工具链暴露为 HTTP 接口供 n8n 调用
端口 8899，所有接口 POST，返回 JSON
"""
import sys
import json
import os
import subprocess
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI()

_MSBIN = Path.home() / "Workbase/Msg-collect/.venv/bin"
_VIDEO_INFO_CMD  = str(_MSBIN / "video-info")
_VIDEO_DL_CMD    = str(_MSBIN / "video-download")
_AUDIO_TR_CMD    = str(_MSBIN / "audio-transcribe")
_AUDIO_SUMM_CMD  = str(_MSBIN / "audio-summarize")
_WORKBASE = Path.home() / "Workbase"

def run_cmd(cmd: str, cwd: str = None) -> dict:
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        cwd=cwd or str(_WORKBASE),
        env={**os.environ, "PATH": f"/opt/homebrew/bin:/usr/local/bin:{os.environ.get('PATH','')}"}
    )
    return {
        "success": result.returncode == 0,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "returncode": result.returncode
    }

def parse_json(stdout: str) -> dict:
    try:
        return json.loads(stdout)
    except:
        return {"stdout": stdout}

@app.post("/video-info")
def video_info(body: dict = None):
    if not body:
        raise HTTPException(400, "body required")
    url = body.get("url", "")
    if not url:
        raise HTTPException(400, "url required")
    r = run_cmd(f'{_VIDEO_INFO_CMD} "{url}"')
    return JSONResponse(content=parse_json(r["stdout"]), status_code=200 if r["success"] else 500)

@app.post("/video-download")
def video_download(body: dict = None):
    if not body:
        raise HTTPException(400, "body required")
    url = body.get("url", "")
    bvid = body.get("bvid", "")
    out_dir = body.get("output", f"/tmp/n8n-pipeline/{bvid}")
    os.makedirs(out_dir, exist_ok=True)
    r = run_cmd(f'{_VIDEO_DL_CMD} "{url}" -o "{out_dir}"')
    return JSONResponse(content=parse_json(r["stdout"]), status_code=200 if r["success"] else 500)

@app.post("/audio-transcribe")
def audio_transcribe(body: dict = None):
    if not body:
        raise HTTPException(400, "body required")
    audio_path = body.get("audio_path", "")
    out_dir = body.get("output", "/tmp/n8n-pipeline")
    os.makedirs(out_dir, exist_ok=True)
    r = run_cmd(f'{_AUDIO_TR_CMD} "{audio_path}" -o "{out_dir}"')
    return JSONResponse(content=parse_json(r["stdout"]), status_code=200 if r["success"] else 500)

@app.post("/audio-summarize")
def audio_summarize(body: dict = None):
    if not body:
        raise HTTPException(400, "body required")
    srt_path = body.get("srt_path", "")
    out_path = body.get("output", "/tmp/n8n-pipeline/summary.md")
    r = run_cmd(
        f'source ~/.hermes/.env 2>/dev/null; '
        f'MINIMAX_CN_API_KEY="$MINIMAX_CN_API_KEY" '
        f'{_AUDIO_SUMM_CMD} "{srt_path}" -o "{out_path}"'
    )
    return JSONResponse(content=parse_json(r["stdout"]), status_code=200 if r["success"] else 500)

@app.get("/ls")
def ls_dir(path: str = "/tmp/n8n-pipeline"):
    p = Path(path)
    if not p.exists():
        return JSONResponse(content={"files": [], "dir": path})
    return JSONResponse(content={"files": sorted([f.name for f in p.iterdir()]), "dir": path})

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
