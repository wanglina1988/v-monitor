#!/usr/bin/env python3
"""测试：无头 Edge + 登录配置 + 页面内 fetch 调雪球接口（关键实验）。"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE = os.path.join(ROOT, ".xq-profile")
API = "https://xueqiu.com/v4/statuses/user_timeline.json?user_id=3533691520&page=1"

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        PROFILE, channel="msedge", headless=True,
        args=["--disable-blink-features=AutomationControlled"],
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    try:
        page.goto("https://xueqiu.com/", wait_until="domcontentloaded", timeout=40000)
        page.wait_for_timeout(5000)
        title = page.title()
        print("首页标题:", title)
        result = page.evaluate("""async (url) => {
            try {
                const r = await fetch(url, {headers: {'accept': 'application/json, text/plain, */*'}});
                const t = await r.text();
                return {status: r.status, len: t.length, head: t.slice(0, 200)};
            } catch (e) { return {error: String(e)}; }
        }""", API)
        print("fetch result:", result)
    except Exception as exc:
        print("ERROR:", exc)
    ctx.close()
