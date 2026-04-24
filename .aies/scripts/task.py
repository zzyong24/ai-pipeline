#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
任务管理脚本。

子命令：
    create <title> [--slug <slug>] [--priority P0|P1|P2|P3]
        创建任务，生成 .aies/tasks/{MM-DD-slug}/task.json
    list
        列出活跃任务
    list-archive
        列出已归档任务
    finish <slug>
        标记任务为 completed
    archive <slug>
        归档任务到 .aies/tasks/archive/{year-month}/
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib.common import (  # noqa: E402
    ensure_developer,
    get_aies_dir,
    month_day,
    now_iso,
    today,
    write_text,
)


def _slugify(text: str) -> str:
    import re
    s = re.sub(r"[^\w\-]+", "-", text.strip().lower())
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "task"


def cmd_create(args: argparse.Namespace) -> int:
    developer = ensure_developer()
    aies = get_aies_dir()
    tasks_dir = aies / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    slug = args.slug or _slugify(args.title)
    dir_name = f"{month_day()}-{slug}"
    task_dir = tasks_dir / dir_name

    if task_dir.exists():
        print(f"❌ 任务目录已存在: {task_dir}", file=sys.stderr)
        return 1

    task_dir.mkdir(parents=True)

    task_data = {
        "slug": slug,
        "title": args.title,
        "status": "planning",
        "priority": args.priority,
        "owner": developer,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "commit": "",
        "parent": None,
        "children": [],
        "related_files": [],
        "notes": "",
    }
    (task_dir / "task.json").write_text(
        json.dumps(task_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # 可选：PRD 模板
    write_text(
        task_dir / "prd.md",
        f"""# {args.title}

## 需求背景

TODO

## 验收标准

- [ ] TODO

## 技术方案

TODO

## 关联资源

- 代码：TODO
- 文档：TODO
""",
    )

    print(f"✅ 任务已创建: {task_dir}")
    print(f"   Slug: {slug}")
    print(f"   Status: planning")
    return 0


def _load_task(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, FileNotFoundError):
        return {}


def cmd_list(_args: argparse.Namespace) -> int:
    aies = get_aies_dir()
    tasks_dir = aies / "tasks"
    if not tasks_dir.is_dir():
        print("(暂无任务)")
        return 0

    active = [
        p for p in sorted(tasks_dir.iterdir())
        if p.is_dir() and p.name != "archive"
    ]
    if not active:
        print("(暂无活跃任务)")
        return 0

    print(f"活跃任务（{len(active)}）:\n")
    print(f"  {'目录':<30} {'状态':<12} {'优先级':<6} 标题")
    print(f"  {'-'*30} {'-'*12} {'-'*6} {'-'*40}")
    for p in active:
        data = _load_task(p / "task.json")
        print(
            f"  {p.name:<30} {data.get('status','unknown'):<12} "
            f"{data.get('priority','-'):<6} {data.get('title','')}"
        )
    return 0


def cmd_list_archive(_args: argparse.Namespace) -> int:
    aies = get_aies_dir()
    archive = aies / "tasks" / "archive"
    if not archive.is_dir():
        print("(暂无归档任务)")
        return 0

    months = sorted(archive.iterdir())
    for m in months:
        if not m.is_dir():
            continue
        print(f"\n## {m.name}")
        for t in sorted(m.iterdir()):
            data = _load_task(t / "task.json")
            print(f"  - {t.name}: {data.get('title', '')}")
    return 0


def _find_task_dir(slug: str) -> Path | None:
    aies = get_aies_dir()
    tasks_dir = aies / "tasks"
    for p in tasks_dir.iterdir():
        if not p.is_dir() or p.name == "archive":
            continue
        if p.name.endswith(f"-{slug}") or p.name == slug:
            return p
    return None


def cmd_finish(args: argparse.Namespace) -> int:
    task_dir = _find_task_dir(args.slug)
    if not task_dir:
        print(f"❌ 未找到任务: {args.slug}", file=sys.stderr)
        return 1

    task_json = task_dir / "task.json"
    data = _load_task(task_json)
    data["status"] = "completed"
    data["updated_at"] = now_iso()
    task_json.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"✅ 任务已标记为 completed: {task_dir.name}")
    print(f"   下一步：python3 .aies/scripts/task.py archive {args.slug}")
    return 0


def cmd_archive(args: argparse.Namespace) -> int:
    task_dir = _find_task_dir(args.slug)
    if not task_dir:
        print(f"❌ 未找到任务: {args.slug}", file=sys.stderr)
        return 1

    from datetime import datetime
    ym = datetime.now().strftime("%Y-%m")
    archive_dir = get_aies_dir() / "tasks" / "archive" / ym
    archive_dir.mkdir(parents=True, exist_ok=True)

    dest = archive_dir / task_dir.name
    if dest.exists():
        print(f"❌ 目标已存在: {dest}", file=sys.stderr)
        return 1

    shutil.move(str(task_dir), str(dest))
    print(f"✅ 任务已归档: {dest}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="task.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    create_p = sub.add_parser("create", help="创建任务")
    create_p.add_argument("title", help="任务标题")
    create_p.add_argument("--slug", default="", help="可选的 slug")
    create_p.add_argument(
        "--priority", default="P2", choices=["P0", "P1", "P2", "P3"]
    )

    sub.add_parser("list", help="列出活跃任务")
    sub.add_parser("list-archive", help="列出已归档任务")

    finish_p = sub.add_parser("finish", help="标记任务完成")
    finish_p.add_argument("slug", help="任务 slug")

    archive_p = sub.add_parser("archive", help="归档任务")
    archive_p.add_argument("slug", help="任务 slug")

    args = parser.parse_args()
    match args.cmd:
        case "create": return cmd_create(args)
        case "list": return cmd_list(args)
        case "list-archive": return cmd_list_archive(args)
        case "finish": return cmd_finish(args)
        case "archive": return cmd_archive(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
