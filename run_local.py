#!/usr/bin/env python3
"""大V动态监控 - 本地工具启动器。

用法：
    python run_local.py                  # 启动网页并自动打开浏览器
    python run_local.py --no-browser     # 不打开浏览器
    python run_local.py --port 9000      # 自定义端口
    python run_local.py --poll           # 开启本地持续轮询（默认关闭，由 GitHub Actions 兜底）
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import webbrowser

# 保证从任意目录运行时都能找到 core/web
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config import load_config          # noqa: E402
from core.githelper import GitHelper         # noqa: E402
from core.log import Logger                  # noqa: E402
from core.pipeline import Pipeline           # noqa: E402
from core.secrets import load_env_file       # noqa: E402
from web.server import WebApp, run_server    # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="大V动态监控 - 本地工具")
    parser.add_argument("--port", type=int, default=None, help="网页端口（默认 8787）")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--poll", action="store_true", help="开启本地持续轮询（默认关闭）")
    parser.add_argument("--interval", type=int, default=None, help="本地轮询间隔（分钟）")
    args = parser.parse_args()

    root = os.path.dirname(os.path.abspath(__file__))
    load_env_file(root)
    config = load_config(root)
    log = Logger(config.data_dir)
    pipeline = Pipeline(config, log=log)
    git = GitHelper()

    if args.port:
        config.data.setdefault("web", {})["port"] = args.port

    port = int(config.web.get("port", 8787))
    host = "0.0.0.0" if config.web.get("allow_lan") else "127.0.0.1"
    url = f"http://127.0.0.1:{port}"

    if args.poll:
        interval = args.interval or int(config.poll_interval_minutes.get("xueqiu", 5))

        def loop() -> None:
            while True:
                try:
                    pipeline.run(push=True, commit=True, git=git, force=False)
                except Exception as exc:
                    log.error(f"本地轮询异常: {exc}")
                time.sleep(interval * 60)

        threading.Thread(target=loop, daemon=True).start()
        log.info(f"本地持续轮询已开启，每 {interval} 分钟一次")

    webapp = WebApp(config, log, pipeline, git)
    try:
        server = run_server(webapp, host, port)
    except OSError as exc:
        log.error(f"端口 {port} 被占用或不可用：{exc}")
        return 1

    log.info(f"网页已启动: {url}（按 Ctrl+C 停止）")
    if config.web.get("access_token"):
        log.info("已设置访问口令，打开页面后需输入口令")
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("已停止")
    return 0


if __name__ == "__main__":
    sys.exit(main())
