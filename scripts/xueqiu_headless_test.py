#!/usr/bin/env python3
"""测试：无头 Edge + 已登录配置 抓雪球接口，能否绕过 WAF。"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE = os.path.join(ROOT, ".xq-profile")
STATE = os.path.join(ROOT, "data", "xueqiu_storage_state.json")
URL = "https://xueqiu.com/v4/statuses/user_timeline.json?user_id=3533691520&page=1"

from playwright.sync_api import sync_playwright


def try_fetch(ctx, label):
    page = ctx.new_page()
    try:
        page.goto(URL, wait_until="domcontentloaded", timeout=40000)
        ok = False
        for i in range(4):
            page.wait_for_timeout(3500)
            content = page.content()
            if content.lstrip().startswith("{"):
                print(f"[{label}] SUCCESS: JSON, len={len(content)}")
                ok = True
                break
            page.goto(page.url, wait_until="domcontentloaded", timeout=40000)
        if not ok:
            print(f"[{label}] WAF/BLOCKED, len={len(page.content())}")
    except Exception as exc:
        print(f"[{label}] ERROR: {exc}")
    finally:
        page.close()


with sync_playwright() as p:
    # 方式 A：同一配置目录 + 无头
    ctx_a = p.chromium.launch_persistent_context(
        PROFILE, channel="msedge", headless=True,
        args=["--disable-blink-features=AutomationControlled"])
    try_fetch(ctx_a, "A:同profile无头")
    ctx_a.close()

    # 方式 B：全新无头 + storage_state(cookies)
    ctx_b = p.chromium.launch(channel="msedge", headless=True,
                              args=["--disable-blink-features=AutomationControlled"])
    if os.path.exists(STATE):
        ctx_b = p.chromium.new_context(storage_state=STATE)
    try_fetch(ctx_b, "B:storage_state无头")
    ctx_b.close()
