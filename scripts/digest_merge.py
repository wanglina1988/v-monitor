#!/usr/bin/env python3
"""雪球速览：增量合并 + 生成 Markdown + 推送。

抓取结果（浏览器里收集）格式：
    [{"name": "拥抱大时代", "url": "https://xueqiu.com/1453667055",
      "posts": [{"info": "作者+时间", "body": "正文", "id": "可选"}]}]

用法：
    python scripts/digest_merge.py <结果.json> [--state data/xueqiu_digest_state.json] [--push] [--title "自定义标题"]
默认标题：{MM月DD日 HH:00 雪球速览}；--push 时调用 scripts/push_digest.py 推送到微信。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def post_id(name: str, post: dict) -> str:
    if post.get("id"):
        return str(post["id"])
    body = post.get("body") or ""
    # 归一化易变内容：视频播放数、长数字等（避免置顶帖播放数变化被误判为“新动态”）
    body = re.sub(r"Play\s*Video\s*\d+", "PlayVideo", body)
    body = re.sub(r"\d{3,}", "N", body)
    return hashlib.sha1((name + "|" + body).encode("utf-8")).hexdigest()[:16]


def main() -> int:
    parser = argparse.ArgumentParser(description="雪球速览增量合并与推送")
    parser.add_argument("result", help="抓取结果 JSON 文件")
    parser.add_argument("--state", default="data/xueqiu_digest_state.json")
    parser.add_argument("--push", action="store_true", help="推送到微信")
    parser.add_argument("--title", default="")
    parser.add_argument("--max-per-user", type=int, default=5)
    args = parser.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    state_path = os.path.join(root, args.state) if not os.path.isabs(args.state) else args.state

    with open(args.result, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 读状态
    state = {}
    if os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            state = {}

    now = datetime.now()
    title = args.title or f"【雪球速览】{now.month}月{now.day}日 {now.hour:02d}:00"
    lines = []
    total_new = 0
    for user in data:
        name = user.get("name", "")
        url = user.get("url", "")
        posts = user.get("posts", [])[: args.max_per_user]
        seen = set(state.get(name, {}).get("seen", []))
        new_posts = []
        for p in posts:
            pid = post_id(name, p)
            if pid in seen:
                continue
            new_posts.append(p)
            seen.add(pid)
        if new_posts:
            total_new += len(new_posts)
            lines.append(f"### {name}")
            for p in new_posts:
                info = (p.get("info") or "").strip()
                body = (p.get("body") or "").strip().replace("\n", " ")
                if len(body) > 90:
                    body = body[:90] + "……"
                lines.append(f"- {info}：{body}")
            if url:
                lines.append(f"[查看主页]({url})")
            lines.append("")
        # 更新状态（保留最近 200 条）
        state.setdefault(name, {})["seen"] = list(seen)[-200:]

    os.makedirs(os.path.dirname(state_path) or ".", exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    print(f"本次新增: {total_new} 条")
    if total_new == 0:
        print("无新增，跳过推送")
        return 0

    content = "\n".join(lines).strip()
    # 保存 markdown 供查看
    md_path = os.path.join(root, "data", "xueqiu_digest_last.md")
    os.makedirs(os.path.dirname(md_path), exist_ok=True)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(content)

    if args.push:
        res = subprocess.run([sys.executable, os.path.join(root, "scripts", "push_digest.py"),
                              "--title", title, "--file", md_path], capture_output=True, text=True)
        print(res.stdout)
        if res.returncode != 0:
            print(res.stderr)
            return res.returncode
    else:
        print("内容已写入 data/xueqiu_digest_last.md（未推送）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
