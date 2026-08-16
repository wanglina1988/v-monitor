"""解析器测试（纯函数，无网络）。"""
import json
import os
import unittest

from core.collectors.xueqiu import parse_comment as xq_comment, parse_status
from core.collectors.weibo import parse_comment as wb_comment, parse_mblog

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def load(name):
    with open(os.path.join(FIX, name), "r", encoding="utf-8") as f:
        return json.load(f)


class TestXueqiuParser(unittest.TestCase):
    def test_parse_post(self):
        raw = load("xueqiu_timeline.json")["statuses"][0]
        it = parse_status(raw)
        self.assertIsNotNone(it)
        self.assertEqual(it.kind, "post")
        self.assertEqual(it.item_id, "10001")
        self.assertEqual(it.user_name, "养猫的叔")
        self.assertEqual(it.text, "今天大盘不错，继续持有。")
        self.assertTrue(it.url.startswith("https://xueqiu.com/1702928600/10001"))
        self.assertEqual(it.published_at, "2026-08-16 09:30:00")
        self.assertGreater(it.ts, 0)

    def test_parse_repost(self):
        raw = load("xueqiu_timeline.json")["statuses"][1]
        self.assertEqual(parse_status(raw).kind, "repost")

    def test_parse_article(self):
        raw = load("xueqiu_timeline.json")["statuses"][2]
        self.assertEqual(parse_status(raw).kind, "article")

    def test_parse_comment(self):
        it = xq_comment({"id": 5001, "body": "<p>说得好</p>",
                         "created_at": "2026-08-16 12:00:00",
                         "user": {"id": 1, "screen_name": "某人"},
                         "status": {"target": "/1/20001"}})
        self.assertEqual(it.kind, "comment")
        self.assertEqual(it.item_id, "c_5001")
        self.assertEqual(it.text, "说得好")
        self.assertTrue(it.url.endswith("/1/20001"))

    def test_parse_bad(self):
        self.assertIsNone(parse_status({}))


class TestWeiboParser(unittest.TestCase):
    def test_parse_post(self):
        cards = load("weibo_timeline.json")["data"]["cards"]
        it = parse_mblog(cards[0]["mblog"], "1234567890")
        self.assertEqual(it.kind, "post")
        self.assertEqual(it.item_id, "5000000001")
        self.assertEqual(it.user_name, "晏凌羊")
        self.assertIn("今天的行情很有意思", it.text)
        self.assertNotIn("<a", it.text)
        self.assertTrue(it.url.endswith("/detail/5000000001"))

    def test_parse_repost(self):
        cards = load("weibo_timeline.json")["data"]["cards"]
        it = parse_mblog(cards[1]["mblog"], "1234567890")
        self.assertEqual(it.kind, "repost")

    def test_parse_comment(self):
        raw = load("weibo_comments.json")["data"]["list"][0]
        it = wb_comment(raw, "1234567890")
        self.assertEqual(it.kind, "comment")
        self.assertEqual(it.item_id, "c_6000000001")
        self.assertEqual(it.text, "说得对，学习了")
        self.assertTrue(it.url.endswith("/999888777/5000000001"))


if __name__ == "__main__":
    unittest.main()
