"""推送渠道选择与消息格式测试（不联网）。"""
import os
import tempfile
import unittest
from unittest.mock import patch

from core.config import AppConfig
from core.models import Item
from core.notifier import (NullNotifier, PushPlusNotifier, WeComNotifier,
                           build_notifier)
from core.util import now_iso


def make_item():
    return Item(platform="xueqiu", user_id="1", user_name="养猫的叔",
                item_id="100", kind="post", text="今天聊聊大盘，内容略长。",
                url="https://xueqiu.com/1/100", published_at=now_iso(), ts=1.0)


def clean_env():
    for k in ("PUSHPLUS_TOKEN", "WECOM_CORPID", "WECOM_SECRET", "WECOM_AGENT_ID"):
        os.environ.pop(k, None)


class TestBuildNotifier(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        clean_env()

    def tearDown(self):
        self.tmp.cleanup()
        clean_env()

    def test_default_pushplus(self):
        os.environ["PUSHPLUS_TOKEN"] = "tok"
        config = AppConfig(self.tmp.name)
        n = build_notifier(config)
        self.assertIsInstance(n, PushPlusNotifier)
        self.assertTrue(n.enabled)

    def test_fallback_wecom(self):
        # 默认 pushplus 但无 token，有企业微信参数 → 回退企业微信
        os.environ["WECOM_CORPID"] = "c"
        os.environ["WECOM_SECRET"] = "s"
        os.environ["WECOM_AGENT_ID"] = "1"
        config = AppConfig(self.tmp.name)
        n = build_notifier(config)
        self.assertIsInstance(n, WeComNotifier)
        self.assertTrue(n.enabled)

    def test_none(self):
        config = AppConfig(self.tmp.name)
        n = build_notifier(config)
        self.assertIsInstance(n, NullNotifier)
        self.assertFalse(n.enabled)

    def test_channel_wecom(self):
        os.environ["WECOM_CORPID"] = "c"
        os.environ["WECOM_SECRET"] = "s"
        os.environ["WECOM_AGENT_ID"] = "1"
        config = AppConfig(self.tmp.name, {"push": {"channel": "wecom"}})
        n = build_notifier(config)
        self.assertIsInstance(n, WeComNotifier)


class TestPushPlusFormat(unittest.TestCase):
    def test_push_item_content(self):
        n = PushPlusNotifier("tok")
        captured = {}

        def fake_send(title, content):
            captured["title"] = title
            captured["content"] = content
            return True

        with patch.object(n, "send_markdown", side_effect=fake_send):
            n.push_item(make_item())
        self.assertIn("养猫的叔", captured["title"])
        self.assertIn("发布了新帖", captured["title"])
        self.assertIn("查看原文", captured["content"])
        self.assertIn("https://xueqiu.com/1/100", captured["content"])
        self.assertIn("今天聊聊大盘", captured["content"])

    def test_push_alert(self):
        n = PushPlusNotifier("tok")
        captured = {}

        def fake_send(title, content):
            captured["title"] = title
            captured["content"] = content
            return True

        with patch.object(n, "send_markdown", side_effect=fake_send):
            n.push_alert("Cookie 失效")
        self.assertIn("提醒", captured["title"])
        self.assertIn("Cookie 失效", captured["content"])


if __name__ == "__main__":
    unittest.main()
