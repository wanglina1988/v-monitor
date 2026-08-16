"""基于标准库的 HTTP 客户端：带重试、超时、JSON 解析。"""
from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class HttpError(Exception):
    def __init__(self, message: str, status: Optional[int] = None, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


def _normalize_cookie(cookie: str) -> str:
    cookie = (cookie or "").strip()
    if cookie.lower().startswith("cookie:"):
        cookie = cookie[len("cookie:"):].strip()
    return cookie


def http_get(url: str, headers: Optional[dict] = None, timeout: float = 20,
             retries: int = 2, backoff: float = 2.0) -> str:
    """GET 请求，返回文本；网络错误/5xx 自动重试。"""
    hdrs = {"User-Agent": DEFAULT_UA}
    if headers:
        hdrs.update(headers)
    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers=hdrs, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            last_exc = HttpError(f"HTTP {exc.code} {url}", status=exc.code, body=body)
            if exc.code < 500 and exc.code not in (408, 429):
                break
        except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as exc:
            last_exc = exc
        if attempt < retries:
            time.sleep(backoff * (attempt + 1))
    raise HttpError(f"请求失败: {last_exc}")


def http_get_json(url: str, headers: Optional[dict] = None, timeout: float = 20,
                  retries: int = 2, backoff: float = 2.0) -> dict:
    text = http_get(url, headers=headers, timeout=timeout, retries=retries, backoff=backoff)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HttpError(f"返回不是合法 JSON: {url} ({exc})") from exc
    if not isinstance(data, dict):
        raise HttpError(f"返回 JSON 结构异常: {url}")
    return data


def http_post_json(url: str, payload: dict, headers: Optional[dict] = None,
                   timeout: float = 20) -> dict:
    hdrs = {"User-Agent": DEFAULT_UA, "Content-Type": "application/json; charset=utf-8"}
    if headers:
        hdrs.update(headers)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        raise HttpError(f"HTTP {exc.code} {url}: {body[:200]}", status=exc.code, body=body)
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as exc:
        raise HttpError(f"请求失败: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise HttpError(f"返回不是合法 JSON: {url} ({exc})") from exc


def cookie_headers(cookie: str, extra: Optional[dict] = None) -> dict:
    hdrs = {"Cookie": _normalize_cookie(cookie)}
    if extra:
        hdrs.update(extra)
    return hdrs
