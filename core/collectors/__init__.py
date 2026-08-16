"""采集器。"""
from .base import CookieInvalidError
from .xueqiu import XueqiuCollector
from .weibo import WeiboCollector


def build_collector(platform: str, cookie: str, log=None, delay: float | None = None):
    if platform == "xueqiu":
        return XueqiuCollector(cookie, delay=delay if delay is not None else 0.5, log=log)
    if platform == "weibo":
        return WeiboCollector(cookie, delay=delay if delay is not None else 2.0, log=log)
    raise ValueError(f"未知平台: {platform}")
