import asyncio
import inspect
import os
import time
from logging import getLogger
from typing import Any, Awaitable, Callable, Dict, Optional, Text

from rasa.core.channels.channel import CollectingOutputChannel, InputChannel, UserMessage
from sanic import Blueprint, response
from sanic.request import Request
from sanic.response import HTTPResponse
from wechatpy.enterprise import WeChatClient, WeChatCrypto, parse_message

logger = getLogger(__name__)


class EnterpriseWechatChannel(InputChannel):
    # 企业微信单条消息最大长度（以字符计）
    MAX_MESSAGE_LENGTH = 500

    def name(self) -> Text:
        return "enterprise_wechat"

    def __init__(self, corp_id, secret, token, aes_key, agent_id, enable_eventbus) -> None:
        super().__init__()

        self.corp_id = corp_id
        self.secret = secret
        self.token = token
        self.aes_key = aes_key
        self.agent_id = agent_id

        self.crypto = WeChatCrypto(token, aes_key, corp_id)

        self.wechat_client = WeChatClient(
            corp_id,
            secret,
        )

        self.bot_id = os.getenv("MUNCHKIN_BOT_ID", "")

    def _send_message_chunks(self, user_id, text: str):
        """分片发送较长的消息"""
        if not text:
            return

        if len(text) <= self.MAX_MESSAGE_LENGTH:
            self.wechat_client.message.send_markdown(self.agent_id, user_id, text)
            return

        # 按最大长度切分消息
        start = 0
        while start < len(text):
            end = start + self.MAX_MESSAGE_LENGTH
            chunk = text[start:end]
            time.sleep(0.2)
            self.wechat_client.message.send_markdown(self.agent_id, user_id, chunk)
            start = end

    @classmethod
    def from_credentials(cls, credentials: Optional[Dict[Text, Any]]) -> "InputChannel":
        return cls(
            credentials.get("corp_id"),
            credentials.get("secret"),
            credentials.get("token"),
            credentials.get("aes_key"),
            credentials.get("agent_id"),
            credentials.get("enable_eventbus", False),
        )

    async def send_message(self, on_new_message, query, reply_user_id):
        try:
            if not query:
                return
            logger.info(f"[Received message]:{query}")

            context = dict()
            context["from_user_id"] = reply_user_id
            collector = CollectingOutputChannel()

            await on_new_message(
                UserMessage(
                    text=query,
                    output_channel=collector,
                    sender_id=reply_user_id,
                    input_channel=self.name(),
                    metadata=None,
                )
            )

            response_data = collector.messages
            reply_text = ("\n\n".join(data["text"] for data in response_data).replace("bot:", "").strip()).replace("\r", "\n")
            reply_text_list = reply_text.split("\n")
            for i in range(0, len(reply_text_list), 50):
                msg = "\n".join(reply_text_list[i : i + 50])
                self._send_message_chunks(reply_user_id, msg)
        except Exception as error:
            logger.error(error)

    def check_signature(self, signature, timestamp, nonce, echostr):
        return self.crypto.check_signature(signature, timestamp, nonce, echostr)

    def blueprint(self, on_new_message: Callable[[UserMessage], Awaitable[None]]) -> Blueprint:
        enterprise_wechathook = Blueprint(
            f"enterprise_wechat_hook_{type(self).__name__}",
            inspect.getmodule(self).__name__,
        )

        @enterprise_wechathook.route("/", methods=["GET"])
        async def index(request: Request) -> HTTPResponse:
            msg_signature = request.args.get("msg_signature")
            timestamp = request.args.get("timestamp")
            nonce = request.args.get("nonce")
            echostr = request.args.get("echostr")

            logger.info(f"Enterprise WeChat verification: msg_signature:{msg_signature}, timestamp:{timestamp}, nonce:{nonce}, echostr:{echostr}")

            echo_str = self.check_signature(msg_signature, timestamp, nonce, echostr)
            return response.text(echo_str)

        @enterprise_wechathook.route("/", methods=["POST"])
        async def msg_entry(request: Request) -> HTTPResponse:
            query_params = request.args
            signature = query_params.get("msg_signature", "")
            timestamp = query_params.get("timestamp", "")
            nonce = query_params.get("nonce", "")

            if request.method == "GET":
                echostr = query_params.get("echostr", "")
                echostr = self.check_signature(signature, timestamp, nonce, echostr)
                return echostr
            elif request.method == "POST":
                message = self.crypto.decrypt_message(request.body, signature, timestamp, nonce)
                message = parse_message(message)
                if message.type == "event":
                    return HTTPResponse(body="")

                if message.type == "text":
                    asyncio.create_task(
                        self.send_message(
                            on_new_message,
                            message.content,
                            message.source,
                        )
                    )

                return HTTPResponse(body="")

        return enterprise_wechathook
