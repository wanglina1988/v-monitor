"""抓取状态：按平台+用户记录已见条目，用于去重。"""
from __future__ import annotations

import json
import os
import time
from typing import Dict, List, Optional

from .util import now_epoch, now_iso

STATE_FILE = "state.json"
SEEN_CAP = 500


class State:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.path = os.path.join(data_dir, STATE_FILE)
        self.data: dict = {"xueqiu": {}, "weibo": {}, "alerts": {}}
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    for k in ("xueqiu", "weibo"):
                        self.data.setdefault(k, {})
                        for uid, rec in (loaded.get(k) or {}).items():
                            if isinstance(rec, dict):
                                self.data[k][str(uid)] = rec
                    alerts = loaded.get("alerts")
                    if isinstance(alerts, dict):
                        self.data["alerts"] = alerts
            except (json.JSONDecodeError, OSError):
                pass

    def save(self) -> None:
        os.makedirs(self.data_dir, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    # ---- 用户级状态 ----
    def _user_rec(self, platform: str, user_id: str, create: bool = True) -> dict:
        bucket = self.data.setdefault(platform, {})
        rec = bucket.get(user_id)
        if rec is None and create:
            rec = {"last_seen": "", "seen": []}
            bucket[user_id] = rec
        return rec or {}

    def seen_ids(self, platform: str, user_id: str) -> set:
        return set(self._user_rec(platform, user_id, create=False).get("seen", []))

    def last_seen(self, platform: str, user_id: str) -> str:
        return self._user_rec(platform, user_id, create=False).get("last_seen", "")

    def add_seen(self, platform: str, user_id: str, item_id: str, published_at: str) -> None:
        rec = self._user_rec(platform, user_id)
        seen = rec.get("seen", [])
        if item_id not in seen:
            seen.append(item_id)
        rec["seen"] = seen[-SEEN_CAP:]
        rec["last_seen"] = published_at or rec.get("last_seen", "")

    # ---- 提醒去重 ----
    def alert_sent_today(self, key: str) -> bool:
        today = time.strftime("%Y-%m-%d", time.localtime())
        alerts = self.data.setdefault("alerts", {})
        return alerts.get(key) == today

    def mark_alert_sent(self, key: str) -> None:
        today = time.strftime("%Y-%m-%d", time.localtime())
        self.data.setdefault("alerts", {})[key] = today

    def merge_remote(self, remote: dict) -> None:
        """合并远端（Actions 提交的）状态到本地，保留本地更新者。"""
        if not isinstance(remote, dict):
            return
        for platform in ("xueqiu", "weibo"):
            for uid, rec in (remote.get(platform) or {}).items():
                if not isinstance(rec, dict):
                    continue
                local = self.data.setdefault(platform, {}).get(str(uid))
                if local is None:
                    self.data[platform][str(uid)] = rec
                else:
                    merged_seen = list(dict.fromkeys(list(local.get("seen", [])) + list(rec.get("seen", []))))
                    self.data[platform][str(uid)]["seen"] = merged_seen[-SEEN_CAP:]
                    ls_local = local.get("last_seen", "")
                    ls_remote = rec.get("last_seen", "")
                    if ls_remote > ls_local:
                        self.data[platform][str(uid)]["last_seen"] = ls_remote
        for k, v in (remote.get("alerts") or {}).items():
            self.data.setdefault("alerts", {})[k] = v
