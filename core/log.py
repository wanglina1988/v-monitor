"""极简日志：同时输出到控制台与 data/logs.txt（环形保留）。"""
from __future__ import annotations

import os
import sys
import threading

from .util import now_iso

MAX_LINES = 600
_lock = threading.Lock()


class Logger:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.logfile = os.path.join(data_dir, "logs.txt")
        os.makedirs(data_dir, exist_ok=True)

    def _write(self, level: str, msg: str) -> None:
        line = f"[{now_iso()}] [{level}] {msg}"
        with _lock:
            try:
                print(line, flush=True)
            except Exception:
                pass
            try:
                with open(self.logfile, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
                self._trim()
            except Exception as exc:  # 日志失败不应影响主流程
                sys.stderr.write(f"log write failed: {exc}\n")

    def _trim(self) -> None:
        try:
            with open(self.logfile, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if len(lines) > MAX_LINES:
                with open(self.logfile, "w", encoding="utf-8") as f:
                    f.writelines(lines[-MAX_LINES:])
        except Exception:
            pass

    def info(self, msg: str) -> None:
        self._write("INFO", msg)

    def warn(self, msg: str) -> None:
        self._write("WARN", msg)

    def error(self, msg: str) -> None:
        self._write("ERROR", msg)

    def tail(self, n: int = 200) -> list:
        try:
            with open(self.logfile, "r", encoding="utf-8") as f:
                lines = f.readlines()
            return lines[-n:]
        except FileNotFoundError:
            return []
