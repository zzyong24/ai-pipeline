#!/usr/bin/env python3
"""
获取 Bilibili Cookie 的工具

方式：读取 ~/.config/yt-dlp/cookies.txt（Netscape 格式，EditThisCookie 导出）
yt-dlp / video-download 直接读这个文件，无需手动配置

用法：
  python3 fetch_cookie.py                    # 读取 cookies.txt，写入 SESSDATA 环境变量
  python3 fetch_cookie.py --check            # 检查 cookie 是否有效
  python3 fetch_cookie.py --export FILE      # 导出到指定路径

依赖：
  - EditThisCookie Chrome 扩展：https://chrome.google.com/webstore/detail/editthiscookie/fngmhnnpilhplaeedifhccceomclgfb
  - 导出格式：Netscape (cookies.txt)
  - 导出路径：~/.config/yt-dlp/cookies.txt
"""
import json
import os
import sys
from pathlib import Path

COOKIE_FILE = Path.home() / ".config/yt-dlp/cookies.txt"


def check_cookie_file(path: Path = COOKIE_FILE) -> dict:
    """检查 cookie 文件是否存在，返回 cookie 内容摘要"""
    if not path.exists():
        return {"status": "missing", "path": str(path)}
    
    with open(path) as f:
        lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
    
    cookies = {}
    for line in lines:
        parts = line.split("\t")
        if len(parts) >= 7 and "bilibili.com" in parts[0]:
            name = parts[5]
            value = parts[6]
            if name in ("SESSDATA", "bili_jct", "DEDEUSERID"):
                cookies[name] = value
    
    has_sessdata = "SESSDATA" in cookies
    return {
        "status": "ok" if has_sessdata else "missing_sessdata",
        "path": str(path),
        "sessdata": cookies.get("SESSDATA", "")[:20] + "..." if cookies.get("SESSDATA") else None,
        "has_bili_jct": "bili_jct" in cookies,
        "has_dedeuserid": "DEDEUSERID" in cookies,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Bilibili Cookie 工具")
    parser.add_argument("--check", action="store_true", help="检查 cookie 文件")
    parser.add_argument("--export", type=str, default=None, help="导出 cookie 到指定文件")
    args = parser.parse_args()
    
    if args.check or (len(sys.argv) == 1 and not os.path.exists(COOKIE_FILE)):
        result = check_cookie_file()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    
    result = check_cookie_file()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    if result["status"] != "ok":
        print("""
❌ Cookie 文件无效或缺失

请按以下步骤操作：
1. 在 Chrome 中安装 EditThisCookie 扩展
   https://chrome.google.com/webstore/detail/editthiscookie/fngmhnnpilhplaeedifhccceomclgfb

2. 登录 Bilibili (https://www.bilibili.com)

3. 点击 EditThisCookie 图标 → 导出 → 选择 "Netscape (cookies.txt)"

4. 保存到 ~/.config/yt-dlp/cookies.txt

5. 确认文件包含 SESSDATA 字段：
   grep SESSDATA ~/.config/yt-dlp/cookies.txt
""", file=sys.stderr)
        sys.exit(1)
    
    print("✅ Cookie 就绪，可直接使用 video-download", file=sys.stderr)


if __name__ == "__main__":
    main()
