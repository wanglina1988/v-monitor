"""主流程测试（使用假采集器与假推送，无网络）。"""
import os
import tempfile
import unittest
from unittest.mock import patch

from core.config import AppConfig
from core.models import CollectorResult, Item
from core.pipeline import Pipeline
from core.util import now_epoch, now_iso


def make_item(platform, uid, iid, ts_offset=60, kind="post"):
    return Item(platform=platform, user_id=uid, user_name="测试", item_id=iid,
                kind=kind, text=f"内容{iid}", url=f"http://x/{iid}",
                published_at=now_iso(), ts=now_epoch() - ts_offset)


class FakeCollector:
    def __init__(self, result):
        self.result = result

    def fetch_user(self, influencer, seen=None):
        return self.result


class FakeNotifier:
    enabled = True

    def __init__(self):
        self.items = []
        self.alerts = []

    def push_item(self, item):
        self.items.append(item.dedup_key())
        return True

    def push_alert(self, text):
        self.alerts.append(text)
        return True


def make_config(tmp, backfill=6):
    data = {
        "poll_interval_minutes": {"xueqiu": 5, "weibo": 10},
        "initial_backfill_hours": backfill,
        "influencers": [
            {"id": "xq_001", "name": "测试", "platform": "xueqiu",
             "user_id": "1702928600", "enabled": True},
        ],
    }
    return AppConfig(tmp, data)


class TestPipeline(unittest.TestCase):
    def setUp(self):
        os.environ["XUEQIU_COOKIE"] = "test-cookie"
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_run_and_dedup(self):
        config = make_config(self.tmp.name)
        notifier = FakeNotifier()
        pipeline = Pipeline(config, notifier=notifier)
        result = CollectorResult(platform="xueqiu", items=[
            make_item("xueqiu", "1702928600", "10001"),
            make_item("xueqiu", "1702928600", "10002"),
        ])
        with patch("core.pipeline.build_collector", return_value=FakeCollector(result)):
            s1 = pipeline.run(platforms=["xueqiu"], push=True, force=True)
        self.assertEqual(s1["new"], 2)
        self.assertEqual(s1["pushed"], 2)
        self.assertEqual(len(notifier.items), 2)
        # 再次运行相同数据：无新增、不重复推送
        with patch("core.pipeline.build_collector", return_value=FakeCollector(result)):
            s2 = pipeline.run(platforms=["xueqiu"], push=True, force=True)
        self.assertEqual(s2["new"], 0)
        self.assertEqual(len(notifier.items), 2)

    def test_first_run_backfill(self):
        config = make_config(self.tmp.name, backfill=1)
        notifier = FakeNotifier()
        pipeline = Pipeline(config, notifier=notifier)
        result = CollectorResult(platform="xueqiu", items=[
            make_item("xueqiu", "1702928600", "old", ts_offset=2 * 3600),  # 超出回填窗口
            make_item("xueqiu", "1702928600", "new", ts_offset=60),
        ])
        with patch("core.pipeline.build_collector", return_value=FakeCollector(result)):
            s = pipeline.run(platforms=["xueqiu"], push=True, force=True)
        self.assertEqual(s["new"], 1)
        self.assertEqual(notifier.items, ["xueqiu:1702928600:new"])
        # 旧条目已标记已见，不重复
        with patch("core.pipeline.build_collector", return_value=FakeCollector(result)):
            s2 = pipeline.run(platforms=["xueqiu"], push=True, force=True)
        self.assertEqual(s2["new"], 0)

    def test_cookie_invalid_alerts_once(self):
        config = make_config(self.tmp.name)
        notifier = FakeNotifier()
        pipeline = Pipeline(config, notifier=notifier)
        result = CollectorResult(platform="xueqiu", items=[], cookie_invalid=True,
                                 error="Cookie 失效")
        with patch("core.pipeline.build_collector", return_value=FakeCollector(result)):
            s1 = pipeline.run(platforms=["xueqiu"], push=True, force=True)
        self.assertIn("xueqiu", s1["cookie_invalid"])
        self.assertEqual(len(notifier.alerts), 1)
        with patch("core.pipeline.build_collector", return_value=FakeCollector(result)):
            s2 = pipeline.run(platforms=["xueqiu"], push=True, force=True)
        self.assertEqual(len(notifier.alerts), 1)  # 每天只提醒一次

    def test_degraded(self):
        config = make_config(self.tmp.name)
        notifier = FakeNotifier()
        pipeline = Pipeline(config, notifier=notifier)
        result = CollectorResult(platform="xueqiu", items=[
            make_item("xueqiu", "1702928600", "10001")],
            comments_ok=False, degraded=True, error="评论接口不可用")
        with patch("core.pipeline.build_collector", return_value=FakeCollector(result)):
            s = pipeline.run(platforms=["xueqiu"], push=True, force=True)
        self.assertIn("xueqiu/测试", s["degraded"])
        self.assertEqual(s["new"], 1)

    def test_no_cookie_skips(self):
        os.environ.pop("XUEQIU_COOKIE", None)
        config = make_config(self.tmp.name)
        notifier = FakeNotifier()
        pipeline = Pipeline(config, notifier=notifier)
        with patch("core.pipeline.build_collector") as fake_build:
            s = pipeline.run(platforms=["xueqiu"], push=True, force=True)
        fake_build.assert_not_called()
        self.assertTrue(any("未配置 Cookie" in e for e in s["errors"]))


if __name__ == "__main__":
    unittest.main()
