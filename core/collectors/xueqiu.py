"""雪球采集器：用户发布/转发/文章 + 最近评论（best-effort）。

接口说明（需登录 Cookie）：
- 用户时间线: https://xueqiu.com/v4/statuses/user_timeline.json?user_id={uid}&page={n}
- 最近评论:   https://xueqiu.com/comments/recent.json?user_id={uid}&page={n} （候选端点）
若评论端点不可用，自动降级为仅发帖/转发/文章，并在结果中标记 degraded。
"""
from __future__ import annotations

import time

from ..http_client import DEFAULT_UA, HttpError, http_get_json
from ..models import CollectorResult, Item
from ..util import iso_zh, now_epoch, parse_zh_datetime, strip_html, to_epoch
from .base import BaseCollector, CookieInvalidError, WAFBlockedError

BASE = "https://xueqiu.com"
COMMENTS_ENDPOINT = "/comments/recent.json"  # 候选端点，确认后可直接修改


def parse_status(raw: dict) -> Item | None:
    sid = raw.get("id")
    if sid is None:
        return None
    item_id = str(sid)
    user = raw.get("user") or {}
    user_name = (user.get("screen_name") or raw.get("user_name") or "").strip() or "未知"
    kind = "post"
    if raw.get("original_status") or raw.get("retweeted_status"):
        kind = "repost"
    elif str(raw.get("type", "")).lower() in ("article", "cub_article", "column"):
        kind = "article"
    text = strip_html(raw.get("description") or raw.get("title") or raw.get("text") or "")
    target = str(raw.get("target") or f"/{sid}")
    if not target.startswith("/"):
        target = "/" + target
    url = BASE + target
    created = raw.get("created_at") or ""
    dt = parse_zh_datetime(created)
    ts = to_epoch(dt) if dt else now_epoch()
    published = iso_zh(dt) if dt else created
    return Item(platform="xueqiu", user_id=str(user.get("id", "")),
                user_name=user_name, item_id=item_id, kind=kind, text=text,
                url=url, published_at=published, ts=ts, raw=raw)


def parse_comment(raw: dict) -> Item | None:
    cid = raw.get("id") or raw.get("comment_id")
    if cid is None:
        return None
    item_id = "c_" + str(cid)
    user = raw.get("user") or {}
    user_name = (user.get("screen_name") or "").strip() or "未知"
    text = strip_html(raw.get("body") or raw.get("content") or raw.get("description") or "")
    status = raw.get("status") or {}
    target = status.get("target") or ""
    if target:
        t = str(target)
        url = BASE + (t if t.startswith("/") else "/" + t)
    else:
        url = f"{BASE}/u/{raw.get('user_id') or user.get('id') or ''}"
    created = raw.get("created_at") or raw.get("time") or ""
    dt = parse_zh_datetime(created)
    ts = to_epoch(dt) if dt else now_epoch()
    published = iso_zh(dt) if dt else created
    return Item(platform="xueqiu", user_id=str(user.get("id", "")),
                user_name=user_name, item_id=item_id, kind="comment", text=text,
                url=url, published_at=published, ts=ts, raw=raw)


class XueqiuCollector(BaseCollector):
    platform = "xueqiu"

    def _headers(self, user_id: str) -> dict:
        return {
            "User-Agent": DEFAULT_UA,
            "Cookie": self.cookie,
            "Referer": f"{BASE}/u/{user_id}",
            "Accept": "application/json, text/plain, */*",
        }

    def _get_json(self, url: str, user_id: str) -> dict:
        try:
            data = http_get_json(url, headers=self._headers(user_id), timeout=20, retries=2)
        except HttpError as exc:
            body = exc.body or ""
            if "aliyun_waf" in body or "renderData" in body or "waf" in body.lower():
                raise WAFBlockedError(f"雪球反爬验证（WAF）拦截，暂时无法抓取；可在浏览器主站复制带通行证的 Cookie 再试") from exc
            self._check_cookie(self.platform, body, status=exc.status)
            raise
        if isinstance(data, dict) and ("error" in data or data.get("error_code")):
            self._check_cookie(self.platform, str(data))
            raise HttpError(f"雪球接口返回错误: {str(data)[:200]}")
        return data

    def fetch_user(self, influencer, seen=None, max_pages: int = 3) -> CollectorResult:
        seen = seen or set()
        uid = influencer.user_id
        items: list[Item] = []
        error = None
        degraded = False
        comments_ok = True
        cookie_invalid = False
        try:
            for page in range(1, max_pages + 1):
                url = f"{BASE}/v4/statuses/user_timeline.json?user_id={uid}&page={page}"
                data = self._get_json(url, uid)
                statuses = data.get("statuses") or data.get("list") or []
                if not statuses:
                    break
                hit_seen = False
                for raw in statuses:
                    item = parse_status(raw)
                    if item is None:
                        continue
                    items.append(item)
                    if item.item_id in seen:
                        hit_seen = True
                if hit_seen:
                    break
                self._sleep()
            # 评论（best-effort，失败降级）
            try:
                items.extend(self.fetch_comments(uid, seen, max_pages=2))
            except CookieInvalidError:
                raise
            except Exception as exc:
                comments_ok = False
                degraded = True
                error = f"评论接口不可用（已降级为仅发帖/转发）: {exc}"
        except CookieInvalidError as exc:
            cookie_invalid = True
            error = str(exc)
        except WAFBlockedError as exc:
            degraded = True
            error = str(exc)
        except Exception as exc:
            error = f"雪球抓取失败: {exc}"
        return CollectorResult(platform=self.platform, items=items,
                               comments_ok=comments_ok, cookie_invalid=cookie_invalid,
                               degraded=degraded, error=error)

    def fetch_comments(self, uid: str, seen=None, max_pages: int = 2) -> list[Item]:
        seen = seen or set()
        items: list[Item] = []
        for page in range(1, max_pages + 1):
            url = f"{BASE}{COMMENTS_ENDPOINT}?user_id={uid}&page={page}"
            data = self._get_json(url, uid)
            comments = data.get("comments") or data.get("list") or []
            if not comments:
                break
            hit_seen = False
            for raw in comments:
                item = parse_comment(raw)
                if item is None:
                    continue
                items.append(item)
                if item.item_id in seen:
                    hit_seen = True
            if hit_seen:
                break
            self._sleep()
        return items
