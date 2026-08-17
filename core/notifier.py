"""推送通知：抽象接口 + PushPlus（默认）+ 企业微信（可选）。"""
from __future__ import annotations

import time
from typing import Optional

from .http_client import HttpError, http_get_json, http_post_json
from .models import KIND_NAMES, PLATFORM_NAMES, Item
from .util import truncate

WECOM_API = "https://qyapi.weixin.qq.com/cgi-bin"
TOKEN_TTL = 7000  # 企业微信 access_token 有效期 7200s，留余量
PUSHPLUS_ENDPOINT = "https://www.pushplus.plus/send"


class Notifier:
    def push_item(self, item: Item) -> bool:
        raise NotImplementedError

    def push_alert(self, text: str) -> bool:
        raise NotImplementedError

    @property
    def enabled(self) -> bool:
        return False


class PushPlusNotifier(Notifier):
    """PushPlus 微信推送（免费每天 200 条，扫码关注公众号即可）。"""

    def __init__(self, token: str):
        self.token = token

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    def send_markdown(self, title: str, content: str) -> bool:
        payload = {
            "token": self.token,
            "title": title,
            "content": content,
            "template": "markdown",
        }
        data = http_post_json(PUSHPLUS_ENDPOINT, payload)
        if data.get("code") != 200:
            raise HttpError(f"PushPlus 发送失败: {data}")
        return True

    def push_item(self, item: Item) -> bool:
        platform = PLATFORM_NAMES.get(item.platform, item.platform)
        action = KIND_NAMES.get(item.kind, "有新动态")
        title = f"【{platform}】{item.user_name} {action}"
        content = (
            f"**时间**：{item.published_at}\n\n"
            f"**内容**：{truncate(item.text, 150) or '（无文字内容，请点开原文）'}\n\n"
            f"[查看原文]({item.url})"
        )
        return self.send_markdown(title, content)

    def push_alert(self, text: str) -> bool:
        return self.send_markdown("⚠️ 大V监控提醒", text)


class WeComNotifier(Notifier):
    """企业微信应用消息推送（免费、无条数限制；需注册企业微信，可选渠道）。"""

    def __init__(self, corpid: str, secret: str, agent_id: str, touser: str = "@all"):
        self.corpid = corpid
        self.secret = secret
        self.agent_id = str(agent_id)
        self.touser = touser or "@all"
        self._token: str = ""
        self._token_expire: float = 0.0

    @property
    def enabled(self) -> bool:
        return bool(self.corpid and self.secret and self.agent_id)

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expire:
            return self._token
        url = f"{WECOM_API}/gettoken?corpid={self.corpid}&corpsecret={self.secret}"
        data = http_get_json(url)
        if data.get("errcode") != 0 or not data.get("access_token"):
            raise HttpError(f"企业微信获取 token 失败: {data}")
        self._token = data["access_token"]
        self._token_expire = time.time() + TOKEN_TTL
        return self._token

    def send_markdown(self, content: str) -> bool:
        token = self._get_token()
        url = f"{WECOM_API}/message/send?access_token={token}"
        payload = {
            "touser": self.touser,
            "msgtype": "markdown",
            "agentid": int(self.agent_id),
            "markdown": {"content": content},
            "safe": 0,
        }
        data = http_post_json(url, payload)
        if data.get("errcode") != 0:
            if data.get("errcode") in (40014, 42001):
                self._token = ""
                token = self._get_token()
                url = f"{WECOM_API}/message/send?access_token={token}"
                data = http_post_json(url, payload)
            if data.get("errcode") != 0:
                raise HttpError(f"企业微信发送失败: {data}")
        return True

    def push_item(self, item: Item) -> bool:
        platform = PLATFORM_NAMES.get(item.platform, item.platform)
        action = KIND_NAMES.get(item.kind, "有新动态")
        content = (
            f"### 【{platform}】{item.user_name} {action}\n"
            f"> **时间**：{item.published_at}\n"
            f"> **内容**：{truncate(item.text, 150) or '（无文字内容，请点开原文）'}\n"
            f"> [查看原文]({item.url})"
        )
        return self.send_markdown(content)

    def push_alert(self, text: str) -> bool:
        content = f"### ⚠️ 大V监控提醒\n> {text}"
        return self.send_markdown(content)


class NullNotifier(Notifier):
    """未配置推送渠道时的空实现（仅记录日志）。"""

    def push_item(self, item: Item) -> bool:
        return False

    def push_alert(self, text: str) -> bool:
        return False


def build_notifier(config) -> Notifier:
    """按 config.push.channel 选择推送渠道；主渠道不可用时回退到另一渠道。"""
    push = config.data.get("push", {})
    channel = push.get("channel", "pushplus")
    token = config.env(push.get("pushplus_token_env", "PUSHPLUS_TOKEN"))
    params = config.wecom_params()
    if channel == "wecom":
        if params:
            return WeComNotifier(**params)
        if token:
            return PushPlusNotifier(token)
    else:  # pushplus（默认）
        if token:
            return PushPlusNotifier(token)
        if params:
            return WeComNotifier(**params)
    return NullNotifier()
