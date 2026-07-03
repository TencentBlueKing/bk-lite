import json
import logging
import re
from typing import Any

import requests
from django.http import HttpRequest, HttpResponse

from apps.opspilot.models import Bot, BotWorkFlow
from apps.opspilot.utils.base_chat_flow_utils import BaseChatFlowUtils
from apps.opspilot.utils.chat_flow_utils.engine.factory import create_chat_flow_engine
from apps.opspilot.utils.enterprise_wechat_aibot_crypto import EnterpriseWechatAibotCrypto, EnterpriseWechatAibotCryptoError
from apps.opspilot.utils.workflow_sensitive_config import decrypt_workflow_sensitive_config

logger = logging.getLogger(__name__)


class EnterpriseWechatAibotChatFlowUtils(BaseChatFlowUtils):
    channel_name = "企微智能机器人"
    channel_code = "enterprise_wechat_aibot"
    cache_key_prefix = "enterprise_wechat_aibot_msg"

    @staticmethod
    def clean_text_message(content: str) -> str:
        return re.sub(r"^@\S+\s*", "", content or "").strip()

    @staticmethod
    def build_flow_input(bot_id: int, node_id: str, message: dict[str, Any], clean_text: str) -> dict[str, Any]:
        sender_id = (message.get("from") or {}).get("userid") or ""
        session_id = message.get("chatid") or sender_id
        return {
            "last_message": clean_text,
            "user_id": sender_id,
            "bot_id": bot_id,
            "node_id": node_id,
            "channel": EnterpriseWechatAibotChatFlowUtils.channel_code,
            "is_third_party": True,
            "entry_type": EnterpriseWechatAibotChatFlowUtils.channel_code,
            "session_id": session_id,
            "response_url": message.get("response_url") or "",
        }

    @classmethod
    def get_aibot_node_config(cls, bot_chat_flow) -> tuple[str | None, dict[str, Any] | None]:
        flow_json = decrypt_workflow_sensitive_config(bot_chat_flow.flow_json or {})
        for node in flow_json.get("nodes", []):
            if node.get("type") == cls.channel_code:
                config = (node.get("data") or {}).get("config") or {}
                return node.get("id"), config
        return None, None

    @classmethod
    def get_webhook_config(cls, config: dict[str, Any]) -> dict[str, Any] | None:
        if config.get("connectionMode", "webhook") != "webhook":
            return None
        webhook = config.get("webhook") or {}
        if not webhook.get("token") or not webhook.get("encodingAESKey"):
            return None
        return webhook

    def handle_request(self, request: HttpRequest) -> HttpResponse:
        bot = Bot.objects.filter(id=self.bot_id, online=True).first()
        if not bot:
            logger.warning("企微智能机器人回调 bot 不存在或未上线: %s", self.bot_id)
            return HttpResponse("success", content_type="text/plain")

        bot_chat_flow = BotWorkFlow.objects.filter(bot_id=bot.id).first()
        if not bot_chat_flow:
            logger.warning("企微智能机器人回调缺少 workflow: %s", self.bot_id)
            return HttpResponse("success", content_type="text/plain")

        node_id, config = self.get_aibot_node_config(bot_chat_flow)
        if not node_id or not config:
            logger.warning("企微智能机器人入口节点不存在: %s", self.bot_id)
            return HttpResponse("success", content_type="text/plain")

        if request.method == "GET":
            return self.handle_url_verification(request, config)
        if request.method == "POST":
            return self.handle_aibot_message(request, node_id, config)
        return HttpResponse("method not allowed", status=405)

    @classmethod
    def handle_url_verification(cls, request: HttpRequest, config: dict[str, Any]) -> HttpResponse:
        webhook = cls.get_webhook_config(config)
        if webhook is None:
            return HttpResponse("fail", status=400)
        crypto = EnterpriseWechatAibotCrypto(
            token=webhook["token"],
            encoding_aes_key=webhook["encodingAESKey"],
        )
        try:
            plaintext = crypto.verify_url(
                msg_signature=request.GET.get("msg_signature", ""),
                timestamp=request.GET.get("timestamp", ""),
                nonce=request.GET.get("nonce", ""),
                echostr=request.GET.get("echostr", ""),
            )
        except EnterpriseWechatAibotCryptoError:
            logger.warning("企微智能机器人 URL 校验失败", exc_info=True)
            return HttpResponse("fail", status=400)
        return HttpResponse(plaintext, content_type="text/plain")

    def handle_aibot_message(self, request: HttpRequest, node_id: str, config: dict[str, Any]) -> HttpResponse:
        webhook = self.get_webhook_config(config)
        if webhook is None:
            logger.warning("企微智能机器人短连接配置无效或模式未启用: %s", self.bot_id)
            return HttpResponse("success", content_type="text/plain")

        crypto = EnterpriseWechatAibotCrypto(
            token=webhook["token"],
            encoding_aes_key=webhook["encodingAESKey"],
        )
        try:
            message = crypto.decrypt_callback(
                msg_signature=request.GET.get("msg_signature", ""),
                timestamp=request.GET.get("timestamp", ""),
                nonce=request.GET.get("nonce", ""),
                body=request.body,
            )
        except EnterpriseWechatAibotCryptoError:
            logger.warning("企微智能机器人消息解密失败: %s", self.bot_id, exc_info=True)
            return HttpResponse("success", content_type="text/plain")

        msg_id = message.get("msgid")
        if not msg_id:
            logger.warning("企微智能机器人消息缺少 msgid: %s", self.bot_id)
            return HttpResponse("success", content_type="text/plain")

        expected_aibotid = webhook.get("aibotid")
        if expected_aibotid and message.get("aibotid") != expected_aibotid:
            logger.warning("企微智能机器人 aibotid 不匹配: bot_id=%s msg_id=%s", self.bot_id, msg_id)
            return HttpResponse("success", content_type="text/plain")

        if self.is_message_processed(msg_id):
            return HttpResponse("success", content_type="text/plain")

        if message.get("msgtype") != "text":
            from apps.opspilot.tasks import process_enterprise_wechat_aibot_reply

            process_enterprise_wechat_aibot_reply.delay(
                self.bot_id,
                msg_id,
                message.get("response_url") or "",
                "当前仅支持文本消息",
            )
            return HttpResponse("success", content_type="text/plain")

        clean_text = self.clean_text_message((message.get("text") or {}).get("content") or "")
        flow_input = self.build_flow_input(bot_id=self.bot_id, node_id=node_id, message=message, clean_text=clean_text)
        task_config = {**config, "node_id": node_id, "response_url": message.get("response_url") or ""}
        from apps.opspilot.tasks import process_enterprise_wechat_aibot_message

        process_enterprise_wechat_aibot_message.delay(
            bot_id=self.bot_id,
            msg_id=msg_id,
            message=flow_input,
            sender_id=flow_input.get("user_id", ""),
            config=task_config,
        )
        return HttpResponse("success", content_type="text/plain")

    @classmethod
    def send_markdown_reply(cls, response_url: str, content: Any) -> None:
        if not response_url:
            return
        final_content = cls.truncate_markdown(cls.format_reply_content(content))
        response = requests.post(
            response_url,
            json={"msgtype": "markdown", "markdown": {"content": final_content}},
            timeout=10,
        )
        response.raise_for_status()
        try:
            response_body = response.json()
        except ValueError as exc:
            raise RuntimeError("企微智能机器人回复接口返回非 JSON 响应") from exc
        if response_body.get("errcode") != 0:
            raise RuntimeError(f"企微智能机器人回复接口返回错误: errcode={response_body.get('errcode')}, " f"errmsg={response_body.get('errmsg')}")

    @staticmethod
    def format_reply_content(content: Any) -> str:
        if content is None or content == "":
            return "处理完成，但未产生可展示内容"
        if isinstance(content, str):
            return content
        if isinstance(content, (dict, list)):
            return json.dumps(content, ensure_ascii=False, indent=2)
        return str(content)

    @staticmethod
    def truncate_markdown(content: str) -> str:
        raw = content.encode("utf-8")
        if len(raw) <= 20480:
            return content
        suffix = "\n\n内容过长，已截断"
        limit = 20480 - len(suffix.encode("utf-8"))
        truncated = raw[:limit].decode("utf-8", errors="ignore")
        return f"{truncated}{suffix}"

    def send_reply(self, reply_text: str, sender_id: str, config: dict[str, Any]):
        self.send_markdown_reply(config.get("response_url") or "", reply_text)

    def execute_chatflow_with_message(self, bot_chat_flow, node_id, message, sender_id):
        engine = create_chat_flow_engine(bot_chat_flow, node_id)
        result = engine.execute(message)
        if isinstance(result, dict):
            if result.get("success") is False:
                return self.format_reply_content(result.get("last_message") or result.get("error") or "处理失败，请稍后重试")
            return self.format_reply_content(result.get("content") or result.get("data") or result.get("last_message") or result)
        return self.format_reply_content(result) if result else "处理完成"
