#!/usr/bin/env python3
"""命令行运行一次监控（本地手动刷新 / GitHub Actions 使用）。

用法：
    python scripts/run_once.py                 # 抓取+推送（不提交）
    python scripts/run_once.py --no-push       # 只抓取记录，不推送
    python scripts/run_once.py --commit        # 抓取+推送+提交回写仓库
    python scripts/run_once.py --platform weibo # 只跑微博
    python scripts/run_once.py --force         # 忽略轮询间隔立即执行
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import load_config        # noqa: E402
from core.githelper import GitHelper       # noqa: E402
from core.log import Logger                # noqa: E402
from core.pipeline import Pipeline         # noqa: E402
from core.secrets import load_env_file     # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="运行一次监控")
    parser.add_argument("--platform", default="all", choices=["all", "xueqiu", "weibo"])
    parser.add_argument("--push", action="store_true", help="推送消息（默认开启，显式声明）")
    parser.add_argument("--no-push", action="store_true", help="不推送消息")
    parser.add_argument("--commit", action="store_true", help="提交并推送数据回仓库")
    parser.add_argument("--force", action="store_true", help="忽略轮询间隔立即执行")
    args = parser.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_env_file(root)
    config = load_config(root)
    log = Logger(config.data_dir)
    pipeline = Pipeline(config, log=log)

    platforms = None if args.platform == "all" else [args.platform]
    summary = pipeline.run(platforms=platforms, push=not args.no_push,
                           commit=args.commit, git=GitHelper(), force=args.force)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    # 致命错误（如配置缺失导致整个平台跳过）返回 1，让 Actions 可见
    fatal = [e for e in summary.get("errors", []) if "未配置 Cookie" in e or "config" in e]
    return 1 if fatal else 0


if __name__ == "__main__":
    sys.exit(main())
