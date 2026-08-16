"""配置加载与保存：config.json + 环境变量。"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from .models import Influencer

CONFIG_FILE = "config.json"

DEFAULTS: Dict[str, Any] = {
    "poll_interval_minutes": {"xueqiu": 5, "weibo": 10},
    "initial_backfill_hours": 6,
    "wecom": {
        "corpid_env": "WECOM_CORPID",
        "secret_env": "WECOM_SECRET",
        "agent_id_env": "WECOM_AGENT_ID",
        "touser": "@all",
    },
    "web": {"port": 8787, "allow_lan": False, "access_token": ""},
    "influencers": [],
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class AppConfig:
    def __init__(self, project_root: str, data: Optional[dict] = None):
        self.project_root = project_root
        self.data = _deep_merge(DEFAULTS, data or {})
        self.influencers: List[Influencer] = [
            Influencer.from_dict(d) for d in self.data.get("influencers", [])
        ]

    # ---- 常用读取 ----
    @property
    def poll_interval_minutes(self) -> dict:
        return self.data.get("poll_interval_minutes", {})

    @property
    def initial_backfill_hours(self) -> float:
        return float(self.data.get("initial_backfill_hours", 6))

    @property
    def wecom(self) -> dict:
        return self.data.get("wecom", {})

    @property
    def web(self) -> dict:
        return self.data.get("web", {})

    @property
    def data_dir(self) -> str:
        d = self.data.get("data_dir")
        if d:
            return d if os.path.isabs(d) else os.path.join(self.project_root, d)
        return os.path.join(self.project_root, "data")

    # ---- 环境变量（密钥） ----
    def env(self, key: str, default: str = "") -> str:
        return os.environ.get(key, default) or default

    def secrets_present(self) -> dict:
        w = self.wecom
        return {
            "wecom_corpid": bool(self.env(w.get("corpid_env", "WECOM_CORPID"))),
            "wecom_secret": bool(self.env(w.get("secret_env", "WECOM_SECRET"))),
            "wecom_agent_id": bool(self.env(w.get("agent_id_env", "WECOM_AGENT_ID"))),
            "xueqiu_cookie": bool(self.env("XUEQIU_COOKIE")),
            "weibo_cookie": bool(self.env("WEIBO_COOKIE")),
        }

    def xueqiu_cookie(self) -> str:
        return self.env("XUEQIU_COOKIE")

    def weibo_cookie(self) -> str:
        return self.env("WEIBO_COOKIE")

    def wecom_params(self) -> Optional[dict]:
        w = self.wecom
        corpid = self.env(w.get("corpid_env", "WECOM_CORPID"))
        secret = self.env(w.get("secret_env", "WECOM_SECRET"))
        agent_id = self.env(w.get("agent_id_env", "WECOM_AGENT_ID"))
        if not (corpid and secret and agent_id):
            return None
        return {"corpid": corpid, "secret": secret, "agent_id": agent_id,
                "touser": w.get("touser") or "@all"}

    # ---- 序列化 ----
    def to_dict(self) -> dict:
        data = dict(self.data)
        data["influencers"] = [inf.to_dict() for inf in self.influencers]
        return data

    def save(self) -> None:
        path = os.path.join(self.project_root, CONFIG_FILE)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
            f.write("\n")

    def find_influencer(self, inf_id: str) -> Optional[Influencer]:
        for inf in self.influencers:
            if inf.id == inf_id:
                return inf
        return None

    def next_influencer_id(self, platform: str) -> str:
        prefix = "xq" if platform == "xueqiu" else "wb"
        used = {inf.id for inf in self.influencers}
        n = len(used) + 1
        while f"{prefix}_{n:03d}" in used:
            n += 1
        return f"{prefix}_{n:03d}"


def load_config(project_root: str) -> AppConfig:
    path = os.path.join(project_root, CONFIG_FILE)
    data: dict = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"config.json 解析失败：{exc}") from exc
    return AppConfig(project_root, data)
