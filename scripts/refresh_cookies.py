#!/usr/bin/env python3
"""交互式获取并保存 雪球/微博 Cookie，并可上传到 GitHub Secrets。

用法：
    python scripts/refresh_cookies.py            # 按提示操作
    python scripts/refresh_cookies.py --test     # 只测试当前已配置的 Cookie 是否有效
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import load_config          # noqa: E402
from core.http_client import HttpError, http_get_json  # noqa: E402
from core.secrets import ENV_FILE, load_env_file  # noqa: E402

_CURL_COOKIE_RE = re.compile(r"-H\s+['\"]cookie:\s*([^'\"]+)['\"]", re.I)
_HEADER_COOKIE_RE = re.compile(r"(?:^|\n)\s*cookie:\s*([^\r\n]+)", re.I)

PLATFORMS = [
    {
        "key": "XUEQIU_COOKIE",
        "name": "雪球",
        "login_url": "https://xueqiu.com",
        "note": "登录后按 F12 → Network → 刷新页面 → 右键任意 xueqiu.com 请求 → Copy as cURL (bash)",
    },
    {
        "key": "WEIBO_COOKIE",
        "name": "微博",
        "login_url": "https://m.weibo.cn",
        "note": "登录后按 F12 → Network → 刷新页面 → 右键任意 m.weibo.cn 请求 → Copy as cURL (bash)",
    },
]


def parse_curl(text: str) -> str:
    m = _CURL_COOKIE_RE.search(text or "")
    if m:
        return m.group(1).strip()
    m = _HEADER_COOKIE_RE.search(text or "")
    if m:
        return m.group(1).strip()
    return ""


def read_env(path: str) -> dict:
    out = {}
    if os.path.exists(path):
        for line in open(path, "r", encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def write_env(path: str, updates: dict) -> None:
    lines = []
    if os.path.exists(path):
        lines = open(path, "r", encoding="utf-8").read().splitlines()
    keys_done = set()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k = stripped.partition("=")[0].strip()
            if k in updates:
                lines[i] = f"{k}={updates[k]}"
                keys_done.add(k)
    for k, v in updates.items():
        if k not in keys_done:
            lines.append(f"{k}={v}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"已写入 {path}")


def probe(platform: str, cookie: str) -> str:
    try:
        if platform == "xueqiu":
            data = http_get_json(
                "https://xueqiu.com/statuses/original/timeline.json?page=1",
                headers={"Cookie": cookie}, retries=0)
            if isinstance(data, dict) and "statuses" in data:
                return "有效（返回了动态数据）"
            if "error" in data or "登录" in str(data):
                return "失效（需要登录）"
            return "响应异常，请人工确认"
        else:
            data = http_get_json(
                "https://m.weibo.cn/api/container/getIndex?type=uid&value=2803301701&containerid=1076032803301701",
                headers={"Cookie": cookie}, retries=0)
            if data.get("ok") == 1:
                return "有效（接口正常返回）"
            return f"可能失效：{data.get('msg', data)}"
    except HttpError as exc:
        if exc.status in (401, 403, 432):
            return f"失效（HTTP {exc.status}）"
        return f"网络/接口错误：{exc}"


def upload_github_secrets(env: dict) -> None:
    print()
    if not shutil.which("gh"):
        print("未检测到 GitHub CLI（gh）。请手动到仓库 Settings → Secrets and variables → Actions 配置：")
        for k, v in env.items():
            if v:
                print(f"  {k} = {v[:6]}…（共 {len(v)} 位）")
        print("完整值见本机 .env.local")
        return
    keys = ["WECOM_CORPID", "WECOM_SECRET", "WECOM_AGENT_ID", "WECOM_TOUSER", "XUEQIU_COOKIE", "WEIBO_COOKIE"]
    print("检测到 gh CLI，将把以下密钥上传到当前仓库 Secrets：")
    for k in keys:
        if env.get(k):
            print(f"  {k} = {env[k][:4]}…")
    ans = input("确认上传？(y/N): ").strip().lower()
    if ans != "y":
        print("已取消。")
        return
    for k in keys:
        v = env.get(k)
        if not v:
            continue
        res = subprocess.run(["gh", "secret", "set", k, "--body", v], capture_output=True, text=True)
        if res.returncode == 0:
            print(f"  {k} 已上传 ✓")
        else:
            print(f"  {k} 上传失败：{res.stderr.strip()[:200]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="刷新 雪球/微博 Cookie")
    parser.add_argument("--test", action="store_true", help="只测试已配置的 Cookie")
    args = parser.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_env_file(root)
    config = load_config(root)
    env_path = os.path.join(root, ENV_FILE)
    env = read_env(env_path)

    if args.test:
        for p in PLATFORMS:
            cookie = env.get(p["key"], "")
            if not cookie:
                print(f"{p['name']} Cookie：未配置")
                continue
            print(f"{p['name']} Cookie：{probe('xueqiu' if p['key'] == 'XUEQIU_COOKIE' else 'weibo', cookie)}")
        return 0

    updates = {}
    print("=" * 60)
    print("请为每个平台提供一个已登录的 Cookie（用浏览器复制 cURL 最快）")
    print("=" * 60)
    for p in PLATFORMS:
        print(f"\n【{p['name']}】")
        print(f"  1. 打开并登录：{p['login_url']}")
        print(f"  2. {p['note']}")
        print(f"  3. 把复制的内容（或直接粘贴 Cookie: 后面的字符串）粘贴到下面")
        raw = input("  粘贴内容（直接回车跳过）: ").strip()
        if not raw:
            print(f"  跳过 {p['name']}")
            continue
        cookie = parse_curl(raw) or raw
        cookie = cookie.strip()
        if "=" not in cookie:
            print("  ⚠️ 内容里没有 Cookie 特征（key=value），已忽略，请重试或手动复制")
            continue
        updates[p["key"]] = cookie
        print(f"  {p['name']} Cookie 已读取（{len(cookie)} 位）")

    if not updates:
        print("未做任何修改。")
        return 0
    env.update(updates)
    write_env(env_path, updates)
    load_env_file(root)
    print("\n测试已保存的 Cookie：")
    for p in PLATFORMS:
        if p["key"] in updates:
            cookie = read_env(env_path).get(p["key"], "")
            print(f"  {p['name']}：{probe('xueqiu' if p['key'] == 'XUEQIU_COOKIE' else 'weibo', cookie)}")
    upload_github_secrets(read_env(env_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
