"""存储测试。"""
import tempfile
import unittest
from unittest.mock import patch

import core.storage as storage_mod
from core.models import Item
from core.storage import Storage


def item(platform, iid, ts):
    return Item(platform=platform, user_id="1", user_name="n", item_id=iid,
                kind="post", text=f"text{iid}", url=f"http://x/{iid}",
                published_at="2026-08-16 09:00:00", ts=ts)


class TestStorage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = Storage(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_append_read(self):
        self.storage.append_items([item("xueqiu", "1", 100.0), item("xueqiu", "2", 200.0)])
        rows = self.storage.read_all(limit=10)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["item_id"], "2")  # 按时间倒序

    def test_filter(self):
        self.storage.append_items([item("xueqiu", "1", 100.0), item("weibo", "2", 200.0)])
        self.assertEqual(len(self.storage.read_all(platform="weibo")), 1)
        self.assertEqual(len(self.storage.read_all(query="text2")), 1)

    def test_trim_per_platform(self):
        with patch.object(storage_mod, "MAX_ITEMS_PER_PLATFORM", 2):
            self.storage.append_items([item("xueqiu", str(i), float(i)) for i in range(5)])
            self.storage.append_items([item("weibo", str(i), float(i)) for i in range(3)])
            self.storage.trim()
        rows = self.storage.read_all(limit=100)
        self.assertEqual(len([r for r in rows if r["platform"] == "xueqiu"]), 2)
        self.assertEqual(len([r for r in rows if r["platform"] == "weibo"]), 2)


if __name__ == "__main__":
    unittest.main()
