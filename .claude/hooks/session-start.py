#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude Code SessionStart Hook — 自动注入 AIES 上下文
"""

import json
import os
import subprocess
import sys
from io import StringIO
from pathlib import Path


def read_file(path: Path, fallback: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError):
        return fallback


def run_script(script: Path) -> str:
    if not script.is_file():
        return ""
    try:
        result = subprocess.run(
            [sys.executable, str(script), "get-context"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=5,
            cwd=script.parent.parent.parent,
        )
        return result.stdout if result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def main() -> int:
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")).resolve()
    aies = project_dir / ".aies"
    ai = project_dir / ".ai"

    out = StringIO()
    out.write("<aies-session>\n")
    out.write("你正在一个由 AIES（AI Engineering Scaffold）管理的项目中工作。\n")
    out.write("下方已为你加载好规范和当前上下文，请严格遵循。\n")
    out.write("</aies-session>\n\n")

    # 当前上下文
    out.write("<current-context>\n")
    out.write(run_script(aies / "scripts" / "session.py") or "(上下文脚本不可用)")
    out.write("\n</current-context>\n\n")

    # Workflow
    out.write("<workflow>\n")
    out.write(read_file(aies / "workflow.md", "(未找到 workflow.md)"))
    out.write("\n</workflow>\n\n")

    # Spec 索引
    out.write("<spec-index>\n")
    out.write(read_file(aies / "spec" / "index.md", "(未找到 spec/index.md)"))
    out.write("\n</spec-index>\n\n")

    # 项目 index
    out.write("<project-index>\n")
    out.write(read_file(ai / "index.md", "(未找到 .ai/index.md)"))
    out.write("\n</project-index>\n\n")

    # Review Checklist
    out.write("<review-checklist>\n")
    out.write(read_file(ai / "review-checklist.md", "(未找到 review-checklist.md)"))
    out.write("\n</review-checklist>\n\n")

    out.write("""<ready>
上下文已加载完毕。
- 收到任务后必须先输出 Phase 1 启动清单
- 写完代码后必须输出 Phase 3 完成清单
- 不要重新读取上述文件，已注入
</ready>""")

    result = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": out.getvalue(),
        }
    }
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
