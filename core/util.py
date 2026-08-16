"""通用工具：时间解析、HTML 清洗、摘要截断。"""
from __future__ import annotations

import datetime as _dt
import html as _html
import re
from typing import Optional

TZ = _dt.timezone(_dt.timedelta(hours=8), name="Asia/Shanghai")
MONTHS = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
          "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}

_TAG_RE = re.compile(r"<[^>]+>")


def now_utc() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def now_iso() -> str:
    return _dt.datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


def now_epoch() -> float:
    return _dt.datetime.now(TZ).timestamp()


def to_epoch(dt: _dt.datetime) -> float:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt.timestamp()


def iso_zh(dt: _dt.datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ).strftime("%Y-%m-%d %H:%M:%S")


def parse_zh_datetime(s: str) -> Optional[_dt.datetime]:
    """解析雪球常见时间 '2026-08-16 12:00:00'（按东八区处理）。"""
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = _dt.datetime.strptime(s, fmt)
            return dt.replace(tzinfo=TZ)
        except ValueError:
            continue
    return None


_WEIBO_TIME_RE = re.compile(
    r"^(?:\w{3},\s*)?(\w{3})\s+(\w{3})\s+(\d{1,2})\s+(\d{2}):(\d{2}):(\d{2})\s+([+-]\d{4})\s+(\d{4})$"
)


def parse_weibo_time(s: str) -> Optional[_dt.datetime]:
    """解析微博时间 'Fri Aug 16 12:00:00 +0800 2026'。"""
    s = (s or "").strip()
    if not s:
        return None
    m = _WEIBO_TIME_RE.match(s)
    if m:
        mon = MONTHS.get(m.group(2))
        if mon:
            try:
                off = int(m.group(7)[:3]) * 60 + int(m.group(7)[3:]) * (1 if m.group(7)[0] == "+" else -1)
                tz = _dt.timezone(_dt.timedelta(minutes=off))
                dt = _dt.datetime(int(m.group(8)), mon, int(m.group(3)),
                                  int(m.group(4)), int(m.group(5)), int(m.group(6)), tzinfo=tz)
                return dt
            except ValueError:
                return None
    dt = parse_zh_datetime(s.replace("T", " "))
    return dt


def strip_html(s: str) -> str:
    """去掉 HTML 标签并还原实体，压缩空白。"""
    if not s:
        return ""
    s = _html.unescape(s)
    s = _TAG_RE.sub("", s)
    s = s.replace("\u200b", "").replace("\u200c", "")
    s = re.sub(r"[ \t\u3000]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def truncate(text: str, n: int = 150) -> str:
    text = (text or "").strip()
    if len(text) <= n:
        return text
    return text[:n].rstrip() + "……"


def mask_secret(value: str, keep: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= keep:
        return "*" * len(value)
    return value[:keep] + "…" + "*" * 4
