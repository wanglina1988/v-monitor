"""微博采集器：用户发帖/转发 + 该用户发表的评论（best-effort，可能受风控降级）。

接口说明（需登录 Cookie）：
- 用户微博: https://m.weibo.cn/api/container/getIndex?type=uid&value={uid}&containerid=107603{uid}&page={n}
- 用户评论: https://weibo.com/ajax/profile/getComments?uid={uid}&page={n}
若评论接口被限流(432/需要登录)，自动降级为仅发帖/转发。
"""
from __future__ import annotations

from ..http_client import DEFAULT_UA, HttpError, http_get_json
from ..models import CollectorResult, Item
from ..util import iso_zh, now_epoch, parse_weibo_time, strip_html, to_epoch
from .base import BaseCollector, CookieInvalidError

M = "https://m.weibo.cn"
WB = "https://weibo.com"


def parse_mblog(mblog: dict, uid: str) -> Item | None:
    mid = mblog.get("id") or mblog.get("mid")
    if not mid:
        return None
    user = mblog.get("user") or {}
    user_name = (user.get("screen_name") or "").strip() or "未知"
    kind = "post"
    if mblog.get("retweeted_status"):
        kind = "repost"
    text = strip_html(mblog.get("text") or "")
    url = f"{M}/detail/{mid}"
    created = mblog.get("created_at") or ""
    dt = parse_weibo_time(created)
    ts = to_epoch(dt) if dt else now_epoch()
    published = iso_zh(dt) if dt else created
    return Item(platform="weibo", user_id=uid, user_name=user_name,
                item_id=str(mid), kind=kind, text=text, url=url,
                published_at=published, ts=ts, raw=mblog)


def parse_comment(raw: dict, uid: str) -> Item | None:
    cid = raw.get("id") or raw.get("cid")
    if cid is None:
        return None
    item_id = "c_" + str(cid)
    user = raw.get("user") or {}
    user_name = (user.get("screen_name") or "").strip() or "我"
    text = strip_html(raw.get("text") or raw.get("comment_text") or "")
    status = raw.get("status") or {}
    status_uid = ""
    mid = ""
    if status:
        su = status.get("user") or {}
        status_uid = str(su.get("id") or status.get("user_id") or "")
        mid = str(status.get("mid") or status.get("id") or "")
    if status_uid and mid:
        url = f"{WB}/{status_uid}/{mid}"
    else:
        url = f"{WB}/u/{uid}"
    created = raw.get("created_at") or ""
    dt = parse_weibo_time(created)
    ts = to_epoch(dt) if dt else now_epoch()
    published = iso_zh(dt) if dt else created
    return Item(platform="weibo", user_id=uid, user_name=user_name,
                item_id=item_id, kind="comment", text=text, url=url,
                published_at=published, ts=ts, raw=raw)


class WeiboCollector(BaseCollector):
    platform = "weibo"

    def _headers(self, uid: str, referer: str) -> dict:
        return {
            "User-Agent": DEFAULT_UA,
            "Cookie": self.cookie,
            "Referer": referer,
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
        }

    def _get_json(self, url: str, uid: str, referer: str) -> dict:
        try:
            data = http_get_json(url, headers=self._headers(uid, referer), timeout=20, retries=1)
        except HttpError as exc:
            self._check_cookie(self.platform, exc.body or "", status=exc.status)
            raise
        if not data.get("ok") and str(data.get("msg", "")).strip():
            self._check_cookie(self.platform, str(data.get("msg")))
        return data

    def fetch_user(self, influencer, seen=None, max_pages: int = 3,
                   include_comments: bool = True) -> CollectorResult:
        seen = seen or set()
        uid = influencer.user_id
        items: list[Item] = []
        error = None
        degraded = False
        comments_ok = True
        cookie_invalid = False
        try:
            for page in range(1, max_pages + 1):
                url = f"{M}/api/container/getIndex?type=uid&value={uid}&containerid=107603{uid}&page={page}"
                data = self._get_json(url, uid, referer=f"{M}/u/{uid}")
                cards = (data.get("data") or {}).get("cards") or []
                hit_seen = False
                got_mblog = False
                for card in cards:
                    if card.get("card_type") != 9:
                        continue
                    got_mblog = True
                    mblog = card.get("mblog") or {}
                    item = parse_mblog(mblog, uid)
                    if item is None:
                        continue
                    items.append(item)
                    if item.item_id in seen:
                        hit_seen = True
                if not cards or hit_seen or not got_mblog:
                    break
                self._sleep()
            if include_comments:
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
        except Exception as exc:
            error = f"微博抓取失败: {exc}"
        return CollectorResult(platform=self.platform, items=items,
                               comments_ok=comments_ok, cookie_invalid=cookie_invalid,
                               degraded=degraded, error=error)

    def fetch_comments(self, uid: str, seen=None, max_pages: int = 2) -> list[Item]:
        seen = seen or set()
        items: list[Item] = []
        for page in range(1, max_pages + 1):
            url = f"{WB}/ajax/profile/getComments?uid={uid}&page={page}"
            data = self._get_json(url, uid, referer=f"{WB}/u/{uid}")
            d = data.get("data") or {}
            lst = d.get("list") or []
            if not lst:
                break
            hit_seen = False
            for raw in lst:
                item = parse_comment(raw, uid)
                if item is None:
                    continue
                items.append(item)
                if item.item_id in seen:
                    hit_seen = True
            if hit_seen:
                break
            self._sleep()
        return items
