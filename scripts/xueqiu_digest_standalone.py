#!/usr/bin/env python3
"""雪球速览 · 独立版：无头 Edge + 专用登录配置 + 页面内 fetch，抓 6 位大V最新动态并推送。

不依赖内置浏览器、不弹窗、浏览器无需常开（脚本按需启动无头 Edge）。
需要先运行 scripts/xueqiu_login_setup.py 完成一次登录（保存到 .xq-profile）。

用法：
    python scripts/xueqiu_digest_standalone.py            # 抓取 + 增量 + 推送
    python scripts/xueqiu_digest_standalone.py --no-push  # 只抓取更新状态，不推送
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import load_config  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE = os.path.join(ROOT, ".xq-profile")
HOME = "https://xueqiu.com/"
API = "https://xueqiu.com/v4/statuses/user_timeline.json?user_id={uid}&page={page}"

_HTML_RE = re.compile(r"<[^>]+>")
INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh']});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
window.chrome = { runtime: {} };
"""


def strip_html(s: str) -> str:
    s = re.sub(_HTML_RE, " ", s or "")
    return re.sub(r"\s+", " ", s).strip()


def fmt_ts(ms) -> str:
    try:
        dt = datetime.fromtimestamp(int(ms) / 1000)
        return dt.strftime("%m-%d %H:%M")
    except Exception:
        return ""


def fetch_user_timeline(ctx, uid, page_holder=None):
    """新开页面，等首页登录态出现后，在页面内 fetch 接口。"""
    page = ctx.new_page()
    page.add_init_script(INIT_SCRIPT)
    try:
        page.goto(HOME, wait_until="domcontentloaded", timeout=40000)
        for _ in range(12):
            try:
                if "我的首页" in page.title():
                    break
            except Exception:
                pass
            page.wait_for_timeout(1500)
        api_url = API.format(uid=uid, page=1)
        data = page.evaluate(
            """async (url) => {
                const r = await fetch(url, {headers: {'accept': 'application/json, text/plain, */*'}});
                const t = await r.text();
                try { return JSON.parse(t); } catch (e) { return {error: t.slice(0,200)}; }
            }""", api_url)
        return data
    finally:
        page.close()


def parse_statuses(name: str, data: dict, max_posts: int):
    posts = []
    for st in (data.get("statuses") or [])[:max_posts]:
        body = strip_html(st.get("description") or st.get("title") or "")
        if not body and st.get("original_status"):
            body = strip_html((st.get("original_status") or {}).get("description") or "")
        if not body:
            continue
        posts.append({
            "id": str(st.get("id") or st.get("target") or ""),
            "info": f"{name} {fmt_ts(st.get('created_at'))}",
            "body": body[:160],
        })
    return posts


def main() -> int:
    parser = argparse.ArgumentParser(description="雪球速览独立版")
    parser.add_argument("--no-push", action="store_true", help="只更新状态，不推送")
    parser.add_argument("--max-per-user", type=int, default=5)
    args = parser.parse_args()

    if not os.path.isdir(PROFILE):
        print("缺少登录配置，请先运行：python scripts/xueqiu_login_setup.py")
        return 2

    config = load_config(ROOT)
    targets = config.data.get("xueqiu_digest", {}).get("targets", [])
    max_posts = args.max_per_user or int(config.data.get("xueqiu_digest", {}).get("max_posts_per_user", 5))

    from playwright.sync_api import sync_playwright

    result = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE, channel="msedge", headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(HOME, wait_until="domcontentloaded", timeout=40000)
            page.wait_for_timeout(4000)
            title = page.title()
            if "我的首页" not in title:
                print(f"未检测到雪球登录态（标题：{title}），请运行 scripts/xueqiu_login_setup.py 重新登录")
                return 3
            for t in targets:
                name = t.get("name", "")
                url = t.get("url", "")
                uid = re.search(r"(\d+)$", url)
                if uid:
                    uid = uid.group(1)
                else:
                    # 别名地址（如 /ysdm）→ 等页面跳转后取数字 ID；失败则从内容提取
                    try:
                        page.goto(url if url.startswith("http") else "https://xueqiu.com" + url,
                                  wait_until="domcontentloaded", timeout=30000)
                        uid = ""
                        for _ in range(8):
                            page.wait_for_timeout(1000)
                            m = re.search(r"/u/(\d+)$", page.url)
                            if m:
                                uid = m.group(1)
                                break
                        if not uid:
                            content = page.content()
                            m2 = re.search(r'["\']?u(?:ser)?[_\-\s]?id["\']?\s*[:=]\s*["\']?(\d{6,})', content)
                            uid = m2.group(1) if m2 else ""
                    except Exception as exc:
                        print(f"[{name}] 解析 ID 失败：{exc}")
                        uid = ""
                print(f"[{name}] uid={uid}")
                if not uid:
                    print(f"[{name}] 未获得 ID，跳过")
                    continue
                data = None
                for attempt in range(3):
                    try:
                        data = fetch_user_timeline(ctx, uid)
                        if "error" in data or "statuses" not in data:
                            print(f"[{name}] 第{attempt + 1}次接口异常：{str(data)[:100]}，重试")
                            data = None
                            continue
                        break
                    except Exception as exc:
                        print(f"[{name}] 第{attempt + 1}次抓取失败：{exc}")
                if data is None or "statuses" not in data:
                    print(f"[{name}] 多次尝试失败，跳过")
                    continue
                posts = parse_statuses(name, data, max_posts)
                result.append({"name": name, "url": url, "posts": posts})
                print(f"[{name}] 接口{len(data.get('statuses', []))}条/解析{len(posts)}条")
        finally:
            ctx.close()

    if not result:
        print("没有抓到任何数据")
        return 1

    tmp = os.path.join(os.environ.get("TEMP", ROOT), "xueqiu_digest_standalone.json")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)

    cmd = [sys.executable, os.path.join(ROOT, "scripts", "digest_merge.py"), tmp]
    if not args.no_push:
        cmd += ["--push"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    print(res.stdout)
    if res.returncode != 0:
        print(res.stderr)
    return res.returncode


if __name__ == "__main__":
    sys.exit(main())
