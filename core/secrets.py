"""加载 .env.local 到环境变量（不会覆盖已有变量）。"""
from __future__ import annotations

import os
from pathlib import Path

ENV_FILE = ".env.local"


def load_env_file(project_root: str) -> None:
    path = Path(project_root) / ENV_FILE
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def get(name: str, default: str = "") -> str:
    return os.environ.get(name, default) or default
