import inspect
import os
from http.client import HTTPResponse
from typing import Any, Awaitable, Callable, Dict, Optional, Text

import requests
from rasa.core.channels import InputChannel, UserMessage
from requests import Request
from sanic import Blueprint, response


class EnterpriseWechatBotChannel(InputChannel):
    def name(self) -> Text:
        return "enterprise_wechat_bot_channel"

    def __init__(self, enterprise_bot_url, secret_token, enable_eventbus) -> None:
        super().__init__()

        self.enterprise_bot_url = enterprise_bot_url
        self.secret_token = secret_token
        self.bot_id = os.getenv("MUNCHKIN_BOT_ID", "")

    def send_enterprise_wechat_bot_message(self, url: str, content: str):
        """
        发送企业微信机器人文本消息
        :param url:
        :param content:
        :return:
        """
        data = {"msgtype": "markdown", "markdown": {"content": content}}
        response = requests.post(url, headers={"Content-Type": "application/json"}, json=data, verify=False)

        return response.json()

    @classmethod
    def from_credentials(cls, credentials: Optional[Dict[Text, Any]]) -> "InputChannel":
        return cls(
            credentials.get("enterprise_bot_url"),
            credentials.get("secret_token"),
            credentials.get("enable_eventbus", False),
        )

    def blueprint(self, on_new_message: Callable[[UserMessage], Awaitable[None]]) -> Blueprint:
        webhook = Blueprint(
            "notification_bot_channel{}".format(type(self).__name__),
            inspect.getmodule(self).__name__,
        )

        @webhook.route("/", methods=["GET"])
        async def index(request: Request) -> HTTPResponse:
            return response.json({"status": "ok"})

        @webhook.route("/", methods=["POST"])
        async def notify(request: Request) -> HTTPResponse:
            if request.args.get("secret_token") != self.secret_token:
                return response.json({"status": "error"}, status=401)

            body = request.json
            content = body.get("content")
            self.send_enterprise_wechat_bot_message(self.enterprise_bot_url, content)
            return response.json({"status": "ok"})

        return webhook
