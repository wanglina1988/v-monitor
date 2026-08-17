"""微博采集器：发帖/转发（weibo.com ajax，已验证可用）+ 评论（best-effort，通常受风控降级）。

接口说明（需登录 Cookie）：
- 发帖/转发（主）：https://weibo.com/ajax/statuses/mymblog?uid={uid}&page={n}&feature=0
- 发帖/转发（回退）：https://m.weibo.cn/api/container/getIndex?type=uid&value={uid}&containerid=107603{uid}&page={n}
- 该用户评论（候选）：https://weibo.com/ajax/profile/getComments?uid={uid}&page={n}
评论接口通常 404/被风控，失败时自动降级为「仅发帖/转发」并在界面标注。
"""
from __future__ import annotations

from ..http_client import DEFAULT_UA, HttpError, http_get_json
from ..models import CollectorResult, Item
from ..util import iso_zh, now_epoch, parse_weibo_time, strip_html, to_epoch
from .base import BaseCollector, CookieInvalidError

M = "https://m.weibo.cn"
WB = "https://weibo.com"
POSTS_ENDPOINT = f"{WB}/ajax/statuses/mymblog"
POSTS_ENDPOINT_FALLBACK = f"{M}/api/container/getIndex"
COMMENTS_ENDPOINT = f"{WB}/ajax/profile/getComments"


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

    # ---------- 发帖/转发 ----------
    def _fetch_posts_weibo_com(self, uid: str, seen: set, max_pages: int) -> list:
        items: list = []
        for page in range(1, max_pages + 1):
            url = f"{POSTS_ENDPOINT}?uid={uid}&page={page}&feature=0"
            data = self._get_json(url, uid, referer=f"{WB}/u/{uid}")
            if data.get("ok") != 1:
                raise HttpError(f"微博 mymblog 返回异常: {str(data)[:150]}")
            lst = (data.get("data") or {}).get("list") or []
            if not lst:
                break
            hit_seen = False
            for raw in lst:
                item = parse_mblog(raw, uid)
                if item is None:
                    continue
                items.append(item)
                if item.item_id in seen:
                    hit_seen = True
            if hit_seen:
                break
            self._sleep()
        return items

    def _fetch_posts_m_weibo_cn(self, uid: str, seen: set, max_pages: int) -> list:
        items: list = []
        for page in range(1, max_pages + 1):
            url = f"{POSTS_ENDPOINT_FALLBACK}?type=uid&value={uid}&containerid=107603{uid}&page={page}"
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
        return items

    def _fetch_posts(self, uid: str, seen: set, max_pages: int) -> list:
        try:
            return self._fetch_posts_weibo_com(uid, seen, max_pages)
        except CookieInvalidError:
            raise
        except Exception as exc:
            self._info(f"weibo.com 接口失败，回退 m.weibo.cn：{exc}")
            try:
                return self._fetch_posts_m_weibo_cn(uid, seen, max_pages)
            except CookieInvalidError:
                raise
            except Exception:
                raise

    # ---------- 评论（best-effort） ----------
    def fetch_comments(self, uid: str, seen=None, max_pages: int = 1) -> list:
        seen = seen or set()
        items: list = []
        for page in range(1, max_pages + 1):
            url = f"{COMMENTS_ENDPOINT}?uid={uid}&page={page}"
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
            items = self._fetch_posts(uid, seen, max_pages)
            if include_comments:
                try:
                    items.extend(self.fetch_comments(uid, seen, max_pages=1))
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
