import asyncio
import base64
import inspect
import os
from logging import getLogger
from typing import Any, Awaitable, Callable, Dict, Optional, Text

import xmltodict
from rasa.core.channels.channel import CollectingOutputChannel, InputChannel, UserMessage
from sanic import Blueprint, response
from sanic.request import Request
from sanic.response import HTTPResponse
from wechatpy import WeChatClient, parse_message
from wechatpy.crypto import PrpCrypto
from wechatpy.utils import check_signature, to_binary, to_text

logger = getLogger(__name__)


class WechatOfficialAccountChannel(InputChannel):
    MAX_MESSAGE_LENGTH = 500

    def name(self) -> Text:
        return "wechat_official_account"

    def __init__(self, appid, secret, token, aes_key, enable_eventbus) -> None:
        super().__init__()

        self.appid = appid
        self.secret = secret
        self.token = token
        encoding_aes_key = to_binary(aes_key + "=")
        self.key = base64.b64decode(encoding_aes_key)
        self.wechat_client = WeChatClient(appid, secret)

        self.bot_id = os.getenv("MUNCHKIN_BOT_ID", "")

    def _send_message_chunks(self, user_id, text: str):
        """分片发送较长的消息"""
        if not text:
            return

        if len(text) <= self.MAX_MESSAGE_LENGTH:
            self.wechat_client.message.send_text(user_id, text)
            return

        # 按最大长度切分消息
        start = 0
        while start < len(text):
            end = start + self.MAX_MESSAGE_LENGTH
            chunk = text[start:end]
            self.wechat_client.message.send_text(user_id, chunk)
            start = end

    def decrypt(self, msg_encrypt):
        pc = PrpCrypto(self.key)
        return pc.decrypt(msg_encrypt, self.appid)

    @classmethod
    def from_credentials(cls, credentials: Optional[Dict[Text, Any]]) -> "InputChannel":
        return cls(
            credentials.get("appid"),
            credentials.get("secret"),
            str(credentials.get("token")),
            credentials.get("aes_key"),
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
            reply_text = "\n\n".join(data["text"] for data in response_data).replace("bot:", "").strip()
            reply_text_list = reply_text.split("\n")
            for i in range(0, len(reply_text_list), 50):
                msg = "\n".join(reply_text_list[i : i + 50])
                self._send_message_chunks(reply_user_id, msg)
                # self.wechat_client.message.send_text(reply_user_id, msg)
        except Exception as error:
            logger.error(error)

    def blueprint(self, on_new_message: Callable[[UserMessage], Awaitable[None]]) -> Blueprint:
        wechat_official_account_hook = Blueprint(
            f"wechat_official_account_hook_{type(self).__name__}",
            inspect.getmodule(self).__name__,
        )

        @wechat_official_account_hook.route("/", methods=["GET"])
        async def index(request: Request) -> HTTPResponse:
            signature = request.args.get("signature")
            timestamp = request.args.get("timestamp")
            nonce = request.args.get("nonce")
            echostr = request.args.get("echostr")

            logger.info(f"WeChat verification: msg_signature:{signature}, timestamp:{timestamp}, nonce:{nonce}, echostr:{echostr}")

            check_signature(self.token, signature, timestamp, nonce)
            return response.text(echostr)

        @wechat_official_account_hook.route("/", methods=["POST"])
        async def msg_entry(request: Request) -> HTTPResponse:
            xml_msg = xmltodict.parse(to_text(request.body))["xml"]
            decode_msg = self.decrypt(xml_msg["Encrypt"])
            message = parse_message(decode_msg)
            if message.type == "text":
                asyncio.create_task(
                    self.send_message(
                        on_new_message,
                        message.content,
                        message.source,
                    )
                )
            return HTTPResponse(body="")

        return wechat_official_account_hook
