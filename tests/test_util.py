"""工具函数测试。"""
import datetime
import unittest

from core.util import parse_weibo_time, parse_zh_datetime, strip_html, to_epoch, truncate


class TestUtil(unittest.TestCase):
    def test_parse_zh_datetime(self):
        dt = parse_zh_datetime("2026-08-16 09:30:00")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.tzinfo.utcoffset(None).total_seconds(), 8 * 3600)

    def test_parse_weibo_time(self):
        dt = parse_weibo_time("Sat Aug 16 09:30:00 +0800 2026")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 8)
        self.assertEqual(dt.hour, 9)
        self.assertAlmostEqual(to_epoch(dt), dt.timestamp(), places=3)

    def test_parse_weibo_time_bad(self):
        self.assertIsNone(parse_weibo_time("not a time"))

    def test_strip_html(self):
        self.assertEqual(strip_html("<p>今天大盘不错，<b>继续持有</b>。</p>"),
                         "今天大盘不错，继续持有。")

    def test_strip_html_entities(self):
        self.assertEqual(strip_html("a &amp; b"), "a & b")

    def test_truncate(self):
        s = "长" * 200
        out = truncate(s, 10)
        self.assertEqual(len(out), 12)
        self.assertTrue(out.endswith("……"))

    def test_truncate_short(self):
        self.assertEqual(truncate("短", 10), "短")


if __name__ == "__main__":
    unittest.main()
