"""采集器公共基类与 Cookie 失效检测。"""
from __future__ import annotations

import time

from ..http_client import HttpError

LOGIN_MARKERS = {
    "xueqiu": ["验证", "verification", "请登录", "登录后", "访问过于频繁", "登陆"],
    "weibo": ["登录", "pincode", "访问过于频繁", "频繁", "passport", "unlogin", "需要登录"],
}


class CookieInvalidError(Exception):
    """Cookie 失效或需要登录。"""


class WAFBlockedError(Exception):
    """平台反爬（如阿里云 WAF JS 验证）拦截，纯 HTTP 无法获取。"""


def detect_cookie_invalid(platform: str, text: str) -> bool:
    text = (text or "")
    low = text.lower()
    for marker in LOGIN_MARKERS.get(platform, []):
        if marker.lower() in low:
            return True
    return False


class BaseCollector:
    platform = ""

    def __init__(self, cookie: str, delay: float = 1.0, log=None):
        self.cookie = cookie
        self.delay = delay
        self.log = log

    def _info(self, msg: str) -> None:
        if self.log:
            self.log.info(msg)

    def _sleep(self) -> None:
        if self.delay > 0:
            time.sleep(self.delay)

    def _check_cookie(self, platform: str, text: str, status=None) -> None:
        if status in (401, 403) or detect_cookie_invalid(platform, text):
            raise CookieInvalidError(f"{platform} Cookie 失效或需要登录 (HTTP {status})")
