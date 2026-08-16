"""网页接口测试（不启动真实端口，直接调用 dispatch）。"""
import tempfile
import unittest

from core.config import AppConfig
from core.log import Logger
from core.models import Item
from core.pipeline import Pipeline
from core.util import now_iso
from web.server import WebApp


def make_config(tmp):
    data = {
        "influencers": [
            {"id": "xq_001", "name": "测试", "platform": "xueqiu",
             "user_id": "1702928600", "enabled": True},
        ],
        "web": {"port": 8787, "allow_lan": False, "access_token": ""},
    }
    return AppConfig(tmp, data)


class TestWeb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = make_config(self.tmp.name)
        self.log = Logger(self.config.data_dir)
        self.pipeline = Pipeline(self.config, log=self.log)
        self.app = WebApp(self.config, self.log, self.pipeline, None)

    def tearDown(self):
        self.tmp.cleanup()

    def test_status(self):
        st, payload = self.app.dispatch("GET", "/api/status", {}, None, None)
        self.assertEqual(st, 200)
        self.assertIn("config", payload)
        self.assertIn("secrets", payload)
        self.assertIn("last_run", payload)

    def test_add_influencer(self):
        st, payload = self.app.dispatch("POST", "/api/influencers", {},
                                        {"name": "新V", "platform": "weibo",
                                         "user_id": "1234567890"}, None)
        self.assertEqual(st, 200, payload)
        self.assertEqual(len(self.config.influencers), 2)
        # 重复
        st2, p2 = self.app.dispatch("POST", "/api/influencers", {},
                                    {"name": "新V2", "platform": "weibo",
                                     "user_id": "1234567890"}, None)
        self.assertEqual(st2, 400)
        # 主页链接形式
        st3, p3 = self.app.dispatch("POST", "/api/influencers", {},
                                    {"name": "雪V", "platform": "xueqiu",
                                     "user_id": "https://xueqiu.com/u/123"}, None)
        self.assertEqual(st3, 200, p3)
        self.assertTrue(any(i.user_id == "123" for i in self.config.influencers))

    def test_toggle_and_delete(self):
        self.app.dispatch("POST", "/api/influencers", {},
                          {"name": "新V", "platform": "weibo", "user_id": "1234567890"}, None)
        inf_id = self.config.influencers[-1].id
        st, p = self.app.dispatch("PUT", f"/api/influencers/{inf_id}", {},
                                  {"enabled": False}, None)
        self.assertEqual(st, 200)
        self.assertFalse(self.config.find_influencer(inf_id).enabled)
        st, p = self.app.dispatch("DELETE", f"/api/influencers/{inf_id}", {}, None, None)
        self.assertEqual(st, 200)
        self.assertIsNone(self.config.find_influencer(inf_id))

    def test_items(self):
        self.pipeline.storage.append_items([
            Item(platform="xueqiu", user_id="1", user_name="a", item_id="1",
                 kind="post", text="hi", url="http://x", published_at=now_iso(), ts=1.0)])
        st, payload = self.app.dispatch("GET", "/api/items", {}, None, None)
        self.assertEqual(st, 200)
        self.assertEqual(len(payload["items"]), 1)

    def test_settings(self):
        st, p = self.app.dispatch("POST", "/api/settings", {},
                                  {"allow_lan": True, "access_token": "abc"}, None)
        self.assertEqual(st, 200)
        self.assertTrue(self.config.web.get("allow_lan"))
        self.assertEqual(self.config.web.get("access_token"), "abc")


if __name__ == "__main__":
    unittest.main()
