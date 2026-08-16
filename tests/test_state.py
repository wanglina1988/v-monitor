"""状态与去重测试。"""
import tempfile
import unittest

from core.state import SEEN_CAP, State


class TestState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = State(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_and_seen(self):
        self.state.add_seen("xueqiu", "1", "a1", "2026-08-16 09:00:00")
        self.state.add_seen("xueqiu", "1", "a2", "2026-08-16 09:05:00")
        self.assertEqual(self.state.seen_ids("xueqiu", "1"), {"a1", "a2"})
        self.assertEqual(self.state.last_seen("xueqiu", "1"), "2026-08-16 09:05:00")

    def test_seen_cap(self):
        for i in range(SEEN_CAP + 50):
            self.state.add_seen("weibo", "2", f"w{i}", "2026-08-16 09:00:00")
        ids = self.state.seen_ids("weibo", "2")
        self.assertEqual(len(ids), SEEN_CAP)
        self.assertIn(f"w{SEEN_CAP + 49}", ids)  # 最新保留
        self.assertNotIn("w0", ids)

    def test_save_reload(self):
        self.state.add_seen("xueqiu", "9", "z1", "2026-08-16 09:00:00")
        self.state.save()
        s2 = State(self.tmp.name)
        self.assertEqual(s2.seen_ids("xueqiu", "9"), {"z1"})

    def test_alert_once(self):
        self.assertFalse(self.state.alert_sent_today("cookie_xueqiu"))
        self.state.mark_alert_sent("cookie_xueqiu")
        self.assertTrue(self.state.alert_sent_today("cookie_xueqiu"))

    def test_merge_remote(self):
        self.state.add_seen("weibo", "1", "a", "2026-08-16 09:00:00")
        remote = {"weibo": {"1": {"seen": ["a", "b"], "last_seen": "2026-08-16 10:00:00"}}}
        self.state.merge_remote(remote)
        self.assertEqual(self.state.seen_ids("weibo", "1"), {"a", "b"})
        self.assertEqual(self.state.last_seen("weibo", "1"), "2026-08-16 10:00:00")


if __name__ == "__main__":
    unittest.main()
