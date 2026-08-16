"""解析用户主页链接/ID → 平台数字 ID。"""
from __future__ import annotations

import re

XUEQIU_RE = re.compile(r"xueqiu\.com/(?:u/)?(\d+)")
WEIBO_RE = re.compile(r"weibo\.com/(?:u/)?(\d+)")


def parse_user_ref(platform: str, raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    if platform == "xueqiu":
        m = XUEQIU_RE.search(raw)
        if m:
            return m.group(1)
        if raw.isdigit():
            return raw
    elif platform == "weibo":
        m = WEIBO_RE.search(raw)
        if m:
            return m.group(1)
        if raw.isdigit():
            return raw
    return ""
