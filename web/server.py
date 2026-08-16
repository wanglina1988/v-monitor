"""本地网页服务：标准库 http.server 实现，无第三方依赖。"""
from __future__ import annotations

import json
import mimetypes
import os
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional, Tuple

from core.config import AppConfig
from core.log import Logger
from core.pipeline import Pipeline
from core.util import mask_secret, now_iso


class WebApp:
    """路由与业务逻辑（与 HTTP 服务器解耦，便于测试）。"""

    def __init__(self, config: AppConfig, log: Logger, pipeline: Pipeline, git):
        self.config = config
        self.log = log
        self.pipeline = pipeline
        self.git = git
        self.static_dir = Path(__file__).parent / "static"

    # ---------- 路由 ----------
    def dispatch(self, method: str, path: str, query: dict, body: Optional[dict],
                 client) -> Tuple[int, dict]:
        routes = {
            ("GET", "/api/items"): lambda: self.api_items(query),
            ("GET", "/api/influencers"): lambda: self.api_influencers(),
            ("POST", "/api/influencers"): lambda: self.api_add_influencer(body or {}),
            ("PUT", "/api/influencers/{id}"): lambda: self.api_update_influencer(self._id_of(path), body or {}),
            ("DELETE", "/api/influencers/{id}"): lambda: self.api_delete_influencer(self._id_of(path)),
            ("GET", "/api/status"): lambda: self.api_status(),
            ("POST", "/api/refresh"): lambda: self.api_refresh(),
            ("POST", "/api/test_push"): lambda: self.api_test_push(),
            ("GET", "/api/logs"): lambda: self.api_logs(),
            ("POST", "/api/settings"): lambda: self.api_settings(body or {}),
        }
        key = (method, path)
        if key not in routes:
            # 尝试带参数路径
            if method in ("PUT", "DELETE") and path.startswith("/api/influencers/"):
                key = (method, "/api/influencers/{id}")
            else:
                return 404, {"error": "接口不存在"}
        try:
            return routes[key]()
        except KeyError:
            return 404, {"error": "接口不存在"}

    @staticmethod
    def _id_of(path: str) -> str:
        return urllib.parse.unquote(path.rsplit("/", 1)[-1])

    # ---------- API 实现 ----------
    def api_items(self, query: dict) -> Tuple[int, dict]:
        platform = (query.get("platform") or [""])[0] or None
        q = (query.get("q") or [""])[0]
        limit = int((query.get("limit") or ["100"])[0])
        offset = int((query.get("offset") or ["0"])[0])
        items = self.pipeline.storage.read_all(platform=platform, limit=limit,
                                               offset=offset, query=q)
        return 200, {"items": items, "count": len(items)}

    def api_influencers(self) -> Tuple[int, dict]:
        out = []
        for inf in self.config.influencers:
            out.append({
                "id": inf.id, "name": inf.name, "platform": inf.platform,
                "user_id": inf.user_id, "enabled": inf.enabled,
                "resolved": inf.resolved,
                "last_seen": self.pipeline.state.last_seen(inf.platform, inf.user_id),
            })
        return 200, {"influencers": out}

    def api_add_influencer(self, body: dict) -> Tuple[int, dict]:
        name = str(body.get("name", "")).strip()
        platform = str(body.get("platform", "")).strip().lower()
        if not name:
            return 400, {"error": "请填写大V名称"}
        if platform not in ("xueqiu", "weibo"):
            return 400, {"error": "平台需为 xueqiu 或 weibo"}
        user_id = self._resolve_user_id(platform, body)
        if not user_id:
            return 400, {"error": "请填写数字 ID 或主页链接（如 https://xueqiu.com/u/123456 或 https://weibo.com/u/1234567890）"}
        if any(i.platform == platform and i.user_id == user_id for i in self.config.influencers):
            return 400, {"error": "该大V已存在"}
        from core.models import Influencer
        inf = {
            "id": self.config.next_influencer_id(platform),
            "name": name, "platform": platform, "user_id": user_id,
            "enabled": True,
        }
        self.config.influencers.append(Influencer.from_dict(inf))
        self.config.save()
        self._sync_git(f"添加大V: {name}")
        return 200, {"influencer": inf}

    def api_update_influencer(self, inf_id: str, body: dict) -> Tuple[int, dict]:
        inf = self.config.find_influencer(inf_id)
        if inf is None:
            return 404, {"error": "未找到该大V"}
        if "enabled" in body:
            inf.enabled = bool(body["enabled"])
        if "name" in body and str(body["name"]).strip():
            inf.name = str(body["name"]).strip()
        if "user_id" in body and str(body["user_id"]).strip():
            inf.user_id = str(body["user_id"]).strip()
        self.config.save()
        self._sync_git(f"更新大V: {inf.name}")
        return 200, {"ok": True}

    def api_delete_influencer(self, inf_id: str) -> Tuple[int, dict]:
        inf = self.config.find_influencer(inf_id)
        if inf is None:
            return 404, {"error": "未找到该大V"}
        self.config.influencers = [i for i in self.config.influencers if i.id != inf_id]
        self.config.save()
        self._sync_git(f"删除大V: {inf.name}")
        return 200, {"ok": True}

    def api_status(self) -> Tuple[int, dict]:
        last = self.pipeline.last_run()
        config_summary = {
            "poll_interval_minutes": self.config.poll_interval_minutes,
            "initial_backfill_hours": self.config.initial_backfill_hours,
            "web": {
                "port": self.config.web.get("port", 8787),
                "allow_lan": bool(self.config.web.get("allow_lan")),
                "access_token_set": bool(self.config.web.get("access_token")),
            },
            "wecom_touser": self.config.wecom.get("touser", "@all"),
        }
        secrets = self.config.secrets_present()
        return 200, {
            "config": config_summary,
            "secrets": secrets,
            "last_run": last,
            "storage_count": self.pipeline.storage.count(),
            "git": {
                "repo": bool(self.git and self.git.is_repo(self.config.project_root)),
                "remote": bool(self.git and self.git.has_remote(self.config.project_root)),
            },
            "server_time": now_iso(),
        }

    def api_refresh(self) -> Tuple[int, dict]:
        if getattr(self, "_refreshing", False):
            return 200, {"started": False, "message": "已有刷新任务进行中"}
        self._refreshing = True

        def worker():
            try:
                self.pipeline.run(push=True, commit=True, git=self.git, force=True)
            except Exception as exc:
                self.log.error(f"手动刷新异常: {exc}")
            finally:
                self._refreshing = False
        threading.Thread(target=worker, daemon=True).start()
        return 200, {"started": True, "message": "刷新已开始，请稍候查看动态"}

    def api_test_push(self) -> Tuple[int, dict]:
        if not self.pipeline.notifier.enabled:
            return 400, {"error": "企业微信推送未配置"}
        try:
            self.pipeline.notifier.push_alert(f"这是一条测试消息：大V监控推送正常 ✅（{now_iso()}）")
            return 200, {"ok": True, "message": "测试消息已发送，请查看微信"}
        except Exception as exc:
            return 500, {"error": f"推送失败: {exc}"}

    def api_logs(self) -> Tuple[int, dict]:
        return 200, {"logs": self.pipeline.log.tail(200)}

    def api_settings(self, body: dict) -> Tuple[int, dict]:
        web = self.config.data.setdefault("web", {})
        if "allow_lan" in body:
            web["allow_lan"] = bool(body["allow_lan"])
        if "access_token" in body:
            web["access_token"] = str(body["access_token"] or "").strip()
        if "poll_interval_minutes" in body and isinstance(body["poll_interval_minutes"], dict):
            self.config.data["poll_interval_minutes"] = body["poll_interval_minutes"]
        self.config.save()
        return 200, {"ok": True, "message": "已保存（允许局域网访问需重启后生效）"}

    # ---------- 辅助 ----------
    def _resolve_user_id(self, platform: str, body: dict) -> str:
        from .resolve import parse_user_ref
        raw = str(body.get("user_id") or body.get("uid") or body.get("url") or "").strip()
        return parse_user_ref(platform, raw)

    def _sync_git(self, message: str) -> None:
        if not self.git:
            return
        try:
            ok, msg = self.git.commit_and_push(self.config.project_root, message, ["config.json"])
            if not ok:
                self.log.warn(f"Git 同步: {msg}")
            else:
                self.log.info(f"Git 同步: {msg}")
        except Exception as exc:
            self.log.warn(f"Git 同步异常: {exc}")



class MonitorHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr, handler, app: WebApp):
        super().__init__(addr, handler)
        self.app = app


class Handler(BaseHTTPRequestHandler):
    server_version = "VMonitor/0.1"

    @property
    def app(self) -> WebApp:
        return self.server.app

    def log_message(self, fmt, *args):
        pass  # 交由应用日志

    def _send(self, status: int, data: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _serve_file(self, rel: str, ctype: str) -> None:
        base = self.app.static_dir.resolve()
        target = (base / rel).resolve()
        if not str(target).startswith(str(base)) or not target.is_file():
            return self._json(404, {"error": "not found"})
        data = target.read_bytes()
        self._send(200, data, ctype)

    def _read_body(self) -> Optional[dict]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def do_PUT(self):
        self._route("PUT")

    def do_DELETE(self):
        self._route("DELETE")

    def _route(self, method: str) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        if path in ("/", "/index.html"):
            return self._serve_file("index.html", "text/html; charset=utf-8")
        if path.startswith("/static/"):
            rel = path[len("/static/"):]
            ctype = mimetypes.guess_type(rel)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript",):
                ctype += "; charset=utf-8"
            return self._serve_file(rel, ctype)
        # API 鉴权
        token = str(self.app.config.web.get("access_token", "") or "")
        if token:
            header_token = self.headers.get("X-Access-Token", "")
            q_token = (query.get("token") or [""])[0]
            if header_token != token and q_token != token:
                return self._json(401, {"error": "需要访问口令"})
        body = self._read_body() if method in ("POST", "PUT") else None
        try:
            status, payload = self.app.dispatch(method, path, query, body, self.client_address)
        except Exception as exc:
            self.app.log.error(f"API {method} {path} 异常: {exc}")
            status, payload = 500, {"error": str(exc)}
        self._json(status, payload)


def run_server(app: WebApp, host: str, port: int) -> MonitorHTTPServer:
    return MonitorHTTPServer((host, port), Handler, app)
