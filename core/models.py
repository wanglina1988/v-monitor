"""数据模型：动态条目与大V配置。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


PLATFORM_NAMES = {"xueqiu": "雪球", "weibo": "微博"}
KIND_NAMES = {"post": "发布了新帖", "repost": "转发了动态", "comment": "发表了评论", "article": "发布了文章"}


@dataclass
class Item:
    """一条大V动态（发帖/转发/评论/文章）。"""
    platform: str                 # xueqiu | weibo
    user_id: str
    user_name: str
    item_id: str                  # 来源平台内的唯一 id
    kind: str                     # post | repost | comment | article
    text: str                     # 纯文本内容（已去 HTML）
    url: str
    published_at: str             # 展示用时间字符串
    ts: float = 0.0               # 排序用 epoch 秒
    raw: dict = field(default_factory=dict, repr=False)

    def dedup_key(self) -> str:
        return f"{self.platform}:{self.user_id}:{self.item_id}"

    def to_line(self) -> dict:
        return {
            "platform": self.platform,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "item_id": self.item_id,
            "kind": self.kind,
            "text": self.text,
            "url": self.url,
            "published_at": self.published_at,
            "ts": self.ts,
        }


@dataclass
class Influencer:
    """一位被关注的大V。"""
    id: str
    name: str
    platform: str                 # xueqiu | weibo
    user_id: str = ""
    enabled: bool = True
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "Influencer":
        user_id = str(d.get("user_id") or d.get("uid") or "")
        return cls(
            id=str(d.get("id", "")),
            name=str(d.get("name", "")).strip(),
            platform=str(d.get("platform", "")).strip().lower(),
            user_id=user_id.strip(),
            enabled=bool(d.get("enabled", True)),
            extra={k: v for k, v in d.items() if k not in ("id", "name", "platform", "user_id", "uid", "enabled")},
        )

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "name": self.name,
            "platform": self.platform,
            "user_id": self.user_id,
            "enabled": self.enabled,
        }
        d.update(self.extra)
        return d

    @property
    def resolved(self) -> bool:
        return bool(self.user_id)


@dataclass
class CollectorResult:
    """一次采集的结果。"""
    platform: str
    items: list = field(default_factory=list)
    comments_ok: bool = True
    cookie_invalid: bool = False
    degraded: bool = False
    error: Optional[str] = None
