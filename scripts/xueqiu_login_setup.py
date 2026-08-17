#!/usr/bin/env python3
"""雪球专用浏览器登录（一次性）：弹出一个 Edge 窗口，扫码/登录雪球一次，
登录状态会保存到专用配置文件（.xq-profile），供无头脚本每小时复用。

用法：
    python scripts/xueqiu_login_setup.py
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE = os.path.join(ROOT, ".xq-profile")


def main() -> int:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE,
            channel="msedge",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://xueqiu.com/", timeout=60000)
        print("=" * 60)
        print("请在刚弹出的 Edge 窗口里登录雪球（扫码或账号密码）。")
        print("登录成功后我会自动检测并保存，约 1-2 分钟无操作则超时。")
        print("=" * 60)
        logged_in = False
        for _ in range(120):
            time.sleep(3)
            try:
                title = page.title()
                body = page.content()
                if "我的首页" in title or "我的首页" in body or "退出账号" in body:
                    logged_in = True
                    break
            except Exception:
                pass
        if logged_in:
            time.sleep(2)
            print("检测到已登录，正在保存登录状态……")
            # 保存 storage state（cookie/本地存储）到 json，供无头模式读取
            state_path = os.path.join(ROOT, "data", "xueqiu_storage_state.json")
            os.makedirs(os.path.dirname(state_path), exist_ok=True)
            ctx.storage_state(path=state_path)
            print(f"已保存到 {state_path}")
            print("完成！现在可以关闭这个窗口，运行 scripts/xueqiu_digest_standalone.py 测试无头抓取。")
        else:
            print("未检测到登录（超时）。可重新运行本脚本。")
        ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
