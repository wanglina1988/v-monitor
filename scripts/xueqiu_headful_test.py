#!/usr/bin/env python3
"""测试：可见 Edge + 已登录配置 + 反自动化特征，抓雪球接口。"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE = os.path.join(ROOT, ".xq-profile")
URL = "https://xueqiu.com/v4/statuses/user_timeline.json?user_id=3533691520&page=1"

INIT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh']});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
window.chrome = { runtime: {} };
"""

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        PROFILE, channel="msedge", headless=False,
        args=["--disable-blink-features=AutomationControlled"],
    )
    for pg in ctx.pages:
        pg.add_init_script(INIT)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.add_init_script(INIT)
    try:
        page.goto(URL, wait_until="domcontentloaded", timeout=40000)
        ok = False
        for i in range(4):
            page.wait_for_timeout(3500)
            content = page.content()
            if content.lstrip().startswith("{"):
                print(f"SUCCESS: JSON len={len(content)}")
                print(content[:200])
                ok = True
                break
            page.goto(page.url, wait_until="domcontentloaded", timeout=40000)
        if not ok:
            print("WAF/BLOCKED len=", len(page.content()))
    except Exception as exc:
        print("ERROR:", exc)
    ctx.close()
