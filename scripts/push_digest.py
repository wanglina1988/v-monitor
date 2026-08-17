#!/usr/bin/env python3
"""把雪球速览（Markdown）推送到微信（PushPlus）。

用法：
    python scripts/push_digest.py --title "标题" --file 内容.md
    python scripts/push_digest.py --title "标题" --content "直接写内容"
读取 .env.local 里的 PUSHPLUS_TOKEN。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.secrets import load_env_file  # noqa: E402

ENDPOINT = "https://www.pushplus.plus/send"


def main() -> int:
    parser = argparse.ArgumentParser(description="推送 Markdown 内容到微信")
    parser.add_argument("--title", required=True, help="消息标题")
    parser.add_argument("--file", help="Markdown 文件路径")
    parser.add_argument("--content", help="直接传内容")
    args = parser.parse_args()

    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            content = f.read()
    elif args.content:
        content = args.content
    else:
        print("请提供 --file 或 --content")
        return 1

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_env_file(root)
    token = os.environ.get("PUSHPLUS_TOKEN", "")
    if not token:
        print("未配置 PUSHPLUS_TOKEN（请在 .env.local 填写）")
        return 1

    payload = json.dumps({
        "token": token,
        "title": args.title,
        "content": content,
        "template": "markdown",
    }).encode("utf-8")
    req = urllib.request.Request(ENDPOINT, data=payload,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=25) as r:
        body = r.read().decode("utf-8", errors="replace")
        print("HTTP", r.status, body)
        data = json.loads(body)
        return 0 if data.get("code") == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
