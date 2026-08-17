"""核心流程：抓取 → 去重 → 推送 → 存储 → 状态更新 → 可选提交回写。"""
from __future__ import annotations

import json
import os
import threading
from typing import List, Optional

from .collectors import build_collector
from .collectors.base import CookieInvalidError
from .config import AppConfig
from .log import Logger
from .models import PLATFORM_NAMES, Item
from .notifier import Notifier, build_notifier
from .state import State
from .storage import Storage
from .util import now_epoch, now_iso

LAST_RUN_FILE = "last_run.json"


class Pipeline:
    def __init__(self, config: AppConfig, log: Optional[Logger] = None,
                 notifier: Optional[Notifier] = None,
                 state: Optional[State] = None, storage: Optional[Storage] = None):
        self.config = config
        self.log = log or Logger(config.data_dir)
        self.notifier = notifier or build_notifier(config)
        self.state = state or State(config.data_dir)
        self.storage = storage or Storage(config.data_dir)
        self._lock = threading.Lock()

    # ---------- 对外入口 ----------
    def run(self, platforms: Optional[List[str]] = None, push: bool = True,
            commit: bool = False, git=None, force: bool = False) -> dict:
        with self._lock:
            return self._run(platforms, push, commit, git, force)

    # ---------- 内部实现 ----------
    def _run(self, platforms, push, commit, git, force) -> dict:
        platforms = platforms or ["xueqiu", "weibo"]
        summary = {
            "started_at": now_iso(),
            "platforms": platforms,
            "fetched": 0,
            "new": 0,
            "pushed": 0,
            "skipped_users": 0,
            "errors": [],
            "degraded": [],
            "cookie_invalid": [],
        }
        if push and not self.notifier.enabled:
            self.log.warn("未配置推送渠道（PushPlus Token 或企业微信参数），本次只记录不推送")

        for platform in platforms:
            if not force and not self._is_due(platform):
                self.log.info(f"[{PLATFORM_NAMES[platform]}] 未到轮询间隔，跳过")
                continue
            cookie = self.config.xueqiu_cookie() if platform == "xueqiu" else self.config.weibo_cookie()
            if not cookie:
                summary["errors"].append(f"{platform}: 未配置 Cookie（请运行 scripts/refresh_cookies.py）")
                self.log.warn(f"[{PLATFORM_NAMES[platform]}] 未配置 Cookie，跳过该平台")
                continue
            collector = build_collector(platform, cookie, log=self.log)
            users = [i for i in self.config.influencers
                     if i.platform == platform and i.enabled and i.resolved]
            if not users:
                self.log.warn(f"[{PLATFORM_NAMES[platform]}] 没有已配置的用户（请先解析大V ID）")
            for inf in users:
                self.log.info(f"[{PLATFORM_NAMES[platform]}] 抓取 {inf.name} ({inf.user_id})")
                try:
                    result = collector.fetch_user(inf, seen=self.state.seen_ids(platform, inf.user_id))
                except CookieInvalidError as exc:
                    summary["cookie_invalid"].append(platform)
                    self.log.error(f"[{PLATFORM_NAMES[platform]}] {inf.name}: {exc}")
                    self._alert_cookie_once(platform, str(exc))
                    continue
                except Exception as exc:
                    summary["errors"].append(f"{platform}/{inf.name}: {exc}")
                    self.log.error(f"[{PLATFORM_NAMES[platform]}] {inf.name} 抓取异常: {exc}")
                    continue

                if result.cookie_invalid:
                    summary["cookie_invalid"].append(platform)
                    self.log.error(f"[{PLATFORM_NAMES[platform]}] {inf.name}: {result.error}")
                    self._alert_cookie_once(platform, result.error or "")
                    continue
                if result.error:
                    summary["errors"].append(f"{platform}/{inf.name}: {result.error}")
                    self.log.warn(f"[{PLATFORM_NAMES[platform]}] {inf.name}: {result.error}")
                if result.degraded:
                    summary["degraded"].append(f"{platform}/{inf.name}")
                    self.log.warn(f"[{PLATFORM_NAMES[platform]}] {inf.name} 评论监控降级")
                if result.items:
                    self.log.info(f"[{PLATFORM_NAMES[platform]}] {inf.name} 抓取到 {len(result.items)} 条")

                new_items = self._select_new(inf, result.items)
                summary["fetched"] += len(result.items)
                if new_items:
                    self.storage.append_items(new_items)
                    for it in new_items:
                        self.state.add_seen(platform, inf.user_id, it.item_id, it.published_at)
                        summary["new"] += 1
                    self.log.info(f"[{PLATFORM_NAMES[platform]}] {inf.name} 新增 {len(new_items)} 条")
                    if push and self.notifier.enabled:
                        for it in new_items:
                            try:
                                self.notifier.push_item(it)
                                summary["pushed"] += 1
                            except Exception as exc:
                                summary["errors"].append(f"推送失败 {it.url}: {exc}")
                                self.log.error(f"推送失败: {exc}")
                else:
                    self.log.info(f"[{PLATFORM_NAMES[platform]}] {inf.name} 无新增")
            self.state.save()

        self._write_last_run(summary)
        self.log.info(f"完成：抓取 {summary['fetched']}，新增 {summary['new']}，推送 {summary['pushed']}"
                      + (f"，错误 {len(summary['errors'])}" if summary["errors"] else ""))
        if commit and git is not None:
            ok, msg = git.commit_and_push(
                self.config.project_root,
                f"monitor: {summary['new']} new items ({now_iso()})",
                ["data/state.json", "data/items.jsonl", "config.json"],
            )
            self.log.info(f"提交回写: {msg}")
            summary["git"] = {"ok": ok, "message": msg}
        return summary

    def _select_new(self, inf, items: List[Item]) -> List[Item]:
        """筛选真正新增的条目；首次运行只回填最近几小时。"""
        seen = self.state.seen_ids(inf.platform, inf.user_id)
        first_run = not self.state.last_seen(inf.platform, inf.user_id)
        backfill_ts = now_epoch() - self.config.initial_backfill_hours * 3600
        new: List[Item] = []
        for it in items:
            if it.item_id in seen:
                continue
            if first_run and it.ts and it.ts < backfill_ts:
                # 首次运行：只推送最近几小时，其余仅记录已见
                self.state.add_seen(inf.platform, inf.user_id, it.item_id, it.published_at)
                continue
            new.append(it)
        return new

    def _is_due(self, platform: str) -> bool:
        interval_min = int(self.config.poll_interval_minutes.get(platform, 10))
        last_ok = self._read_last_run().get("platforms", {}).get(platform, 0.0)
        return (now_epoch() - last_ok) >= interval_min * 60

    def _alert_cookie_once(self, platform: str, detail: str) -> None:
        key = f"cookie_{platform}"
        if self.state.alert_sent_today(key):
            return
        if self.notifier.enabled:
            try:
                self.notifier.push_alert(
                    f"{PLATFORM_NAMES[platform]} 的 Cookie 已失效或需要重新登录。\n"
                    f"请在本机运行：python scripts/refresh_cookies.py\n"
                    f"详情：{detail}"
                )
                self.log.info(f"已推送 {PLATFORM_NAMES[platform]} Cookie 失效提醒")
            except Exception as exc:
                self.log.error(f"Cookie 提醒推送失败: {exc}")
        self.state.mark_alert_sent(key)
        self.state.save()

    # ---------- last_run ----------
    def _last_run_path(self) -> str:
        return os.path.join(self.config.data_dir, LAST_RUN_FILE)

    def _read_last_run(self) -> dict:
        try:
            with open(self._last_run_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _write_last_run(self, summary: dict) -> None:
        last = self._read_last_run()
        platforms = last.get("platforms", {})
        finished = now_epoch()
        for p in summary.get("platforms", []):
            platforms[p] = finished
        last["platforms"] = platforms
        last["finished_at"] = now_iso()
        last["finished_at_epoch"] = finished
        last["summary"] = summary
        try:
            with open(self._last_run_path(), "w", encoding="utf-8") as f:
                json.dump(last, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            self.log.error(f"写入 last_run.json 失败: {exc}")

    def last_run(self) -> dict:
        return self._read_last_run()
