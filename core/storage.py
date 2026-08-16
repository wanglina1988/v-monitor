"""历史条目存储：data/items.jsonl（每个平台保留最近 2000 条）。"""
from __future__ import annotations

import json
import os
from typing import List, Optional

from .models import Item

ITEMS_FILE = "items.jsonl"
MAX_ITEMS_PER_PLATFORM = 2000


class Storage:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.path = os.path.join(data_dir, ITEMS_FILE)
        os.makedirs(data_dir, exist_ok=True)
        if not os.path.exists(self.path):
            open(self.path, "w", encoding="utf-8").close()

    def append_items(self, items: List[Item]) -> None:
        if not items:
            return
        with open(self.path, "a", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it.to_line(), ensure_ascii=False) + "\n")
        self.trim()

    def read_all(self, platform: Optional[str] = None, limit: int = 200,
                 offset: int = 0, query: str = "", kinds: Optional[List[str]] = None) -> List[dict]:
        rows: List[dict] = []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    rows.append(row)
        except FileNotFoundError:
            return []
        rows.sort(key=lambda r: r.get("ts", 0), reverse=True)
        out: List[dict] = []
        q = (query or "").strip().lower()
        for r in rows:
            if platform and r.get("platform") != platform:
                continue
            if q and q not in (r.get("text", "") + r.get("user_name", "")).lower():
                continue
            if kinds and r.get("kind") not in kinds:
                continue
            out.append(r)
        return out[offset:offset + limit]

    def count(self) -> int:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return sum(1 for line in f if line.strip())
        except FileNotFoundError:
            return 0

    def trim(self) -> None:
        """每个平台只保留最近 MAX_ITEMS_PER_PLATFORM 条。"""
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                lines = [ln for ln in f if ln.strip()]
        except FileNotFoundError:
            return
        per: dict = {}
        for ln in lines:
            try:
                row = json.loads(ln)
            except json.JSONDecodeError:
                continue
            per.setdefault(row.get("platform", "?"), []).append(ln)
        keep = []
        for platform, plines in per.items():
            plines.sort(key=lambda x: _line_ts(x), reverse=True)
            keep.extend(plines[:MAX_ITEMS_PER_PLATFORM])
        keep.sort(key=_line_ts)
        if len(keep) != len(lines):
            with open(self.path, "w", encoding="utf-8") as f:
                f.writelines(keep)


def _line_ts(line: str) -> float:
    try:
        return float(json.loads(line).get("ts", 0.0))
    except Exception:
        return 0.0
