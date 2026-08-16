#!/usr/bin/env python3
"""解析/补全大V的数字 ID（首次配置必跑一次）。

- 雪球：尝试用户搜索接口；失败则让你粘贴主页链接（xueqiu.com/u/123456）
- 微博：调用搜索建议接口列出同名账号，人工确认选择（同名账号很多，必须人工确认）

用法：
    python scripts/resolve_influencers.py
"""
from __future__ import annotations

import argparse
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import load_config              # noqa: E402
from core.http_client import HttpError, http_get_json  # noqa: E402
from core.secrets import load_env_file           # noqa: E402
from web.resolve import parse_user_ref           # noqa: E402


def resolve_xueqiu(name: str, cookie: str):
    candidates = []
    for endpoint in (
        f"https://xueqiu.com/query/v1/search/user.json?q={urllib.parse.quote(name)}&count=5",
        f"https://xueqiu.com/query/v1/search/status.json?q={urllib.parse.quote(name)}&count=5",
    ):
        try:
            data = http_get_json(endpoint, headers={"Cookie": cookie} if cookie else {}, retries=0)
        except (HttpError, Exception):
            continue
        lst = (data.get("data") or {}).get("list") or data.get("list") or []
        for u in lst:
            uid = u.get("id") or u.get("user_id")
            sn = u.get("screen_name") or u.get("name") or u.get("user", {}).get("screen_name") or ""
            if uid and sn:
                candidates.append((str(uid), str(sn), "雪球用户"))
        if candidates:
            break
    return candidates


def resolve_weibo(name: str, cookie: str):
    url = f"https://m.weibo.cn/api/container/getIndex?type=suggestion&value={urllib.parse.quote(name)}"
    try:
        data = http_get_json(url, headers={"Cookie": cookie} if cookie else {}, retries=0)
    except HttpError as exc:
        print(f"  ⚠️ 微博搜索建议接口失败：{exc}")
        return []
    lst = (data.get("data") or {}).get("list") or []
    out = []
    for u in lst:
        uid = u.get("id")
        sn = u.get("screen_name") or u.get("name")
        desc = (u.get("description") or u.get("followers_count") or "")[:40]
        if uid and sn:
            out.append((str(uid), str(sn), str(desc)))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="解析大V ID")
    parser.add_argument("--keep", action="store_true", help="已解析的保持不变")
    args = parser.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_env_file(root)
    config = load_config(root)
    cookie_xq = config.xueqiu_cookie()
    cookie_wb = config.weibo_cookie()

    print("开始解析大V ID（网络请求，请稍候）……")
    changed = 0
    for inf in config.influencers:
        if inf.resolved and args.keep:
            print(f"  - {inf.name}：已解析 {inf.user_id}，跳过")
            continue
        print(f"\n== {inf.name}（{'雪球' if inf.platform == 'xueqiu' else '微博'}）==")
        if inf.platform == "xueqiu":
            candidates = resolve_xueqiu(inf.name, cookie_xq)
        else:
            candidates = resolve_weibo(inf.name, cookie_wb)
        if candidates:
            print("  找到以下账号：")
            for i, (uid, sn, extra) in enumerate(candidates, 1):
                print(f"    [{i}] {sn}  (ID: {uid})  {extra}")
            choice = input("  输入编号选择，或直接粘贴主页链接/ID（回车跳过）: ").strip()
        else:
            choice = input("  未能自动匹配，请粘贴主页链接或数字 ID（回车跳过）: ").strip()
        ref = choice
        if ref and ref.isdigit() and len(candidates) and 1 <= int(ref) <= len(candidates):
            ref = candidates[int(ref) - 1][0]
        uid = parse_user_ref(inf.platform, ref)
        if uid:
            inf.user_id = uid
            changed += 1
            print(f"  ✓ 已设置 {inf.name} → {uid}")
        else:
            print("  - 跳过（保持未解析，之后可在网页「管理」中填写）")

    if changed:
        config.save()
        print(f"\n完成，已更新 {changed} 位大V。可运行 python run_local.py 查看。")
    else:
        print("\n没有更新。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
