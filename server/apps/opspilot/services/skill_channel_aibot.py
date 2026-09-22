"""智能体企微智能机器人（aibot）渠道：复用 Bot 协议，执行单 Agent。"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest, HttpResponse, JsonResponse

from apps.core.logger import opspilot_logger as logger
from apps.core.logger import safe_log_value
from apps.opspilot.enum import SkillChannelChoices
from apps.opspilot.models import SkillChannel
from apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils import EnterpriseWechatAibotChatFlowUtils
from apps.opspilot.utils.enterprise_wechat_aibot_crypto import EnterpriseWechatAibotCrypto, EnterpriseWechatAibotCryptoError

SKILL_CHANNEL_AIBOT_DECRYPT_FAILED_TEMPLATE = (
    "event=skill_channel_aibot_decrypt_failed channel_id=%s failed_stage=decrypt_callback "
    "error_type=%s has_msg_signature=%s has_timestamp=%s has_nonce=%s token_len=%s"
)


def normalize_aibot_channel_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """将 SkillChannel.channel_config 规范为 Bot aibot 节点 webhook 形态。"""
    config = dict(config or {})
    if config.get("webhook") or config.get("connectionMode"):
        out = dict(config)
        out.setdefault("connectionMode", "webhook")
        return out

    token = config.get("token")
    aes_key = config.get("encodingAESKey") or config.get("aes_key")
    webhook: dict[str, Any] = {}
    if isinstance(token, str):
        token = token.strip()
    if isinstance(aes_key, str):
        aes_key = aes_key.strip()
    if token:
        webhook["token"] = token
    if aes_key:
        webhook["encodingAESKey"] = aes_key
    return {"connectionMode": "webhook", "webhook": webhook}


class SkillChannelAibotUtils(EnterpriseWechatAibotChatFlowUtils):
    """去重键使用 channel_id；协议方法继承自 Bot aibot utils。"""

    channel_name = "智能体企微机器人"
    channel_code = "enterprise_wechat_aibot"
    cache_key_prefix = "skill_channel_aibot_msg"

    def __init__(self, channel_id: int):
        super().__init__(channel_id)
        self.channel_id = channel_id

    def handle_request(self, request: HttpRequest) -> HttpResponse:
        channel = SkillChannel.objects.filter(
            id=self.channel_id,
            channel_type=SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT,
        ).first()
        if not channel or not channel.enabled:
            if request.method == "GET":
                return HttpResponse("fail", status=403)
            return JsonResponse({"result": False, "message": "渠道不存在或已下线"}, status=403)

        config = normalize_aibot_channel_config(channel.channel_config)
        if request.method == "GET":
            return self.handle_url_verification(request, config)
        if request.method == "POST":
            return self.handle_aibot_message(request, config)
        return HttpResponse("method not allowed", status=405)

    def handle_aibot_message(self, request: HttpRequest, config: dict[str, Any]) -> HttpResponse:
        webhook = self.get_webhook_config(config)
        if webhook is None:
            logger.warning("智能体企微机器人短连接配置无效 channel_id=%s", self.channel_id)
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
        except EnterpriseWechatAibotCryptoError as exc:
            logger.warning(
                SKILL_CHANNEL_AIBOT_DECRYPT_FAILED_TEMPLATE,
                self.channel_id,
                safe_log_value(exc.args[0] if exc.args else type(exc).__name__),
                bool(request.GET.get("msg_signature")),
                bool(request.GET.get("timestamp")),
                bool(request.GET.get("nonce")),
                len((webhook.get("token") or "").strip()),
            )
            return HttpResponse("success", content_type="text/plain")

        msg_id = message.get("msgid")
        if not msg_id:
            logger.warning("智能体企微机器人消息缺少 msgid channel_id=%s", self.channel_id)
            return HttpResponse("success", content_type="text/plain")

        if self.is_message_processed(msg_id):
            return HttpResponse("success", content_type="text/plain")

        if message.get("msgtype") != "text":
            from apps.opspilot.tasks import process_skill_channel_aibot_reply

            process_skill_channel_aibot_reply.delay(
                self.channel_id,
                msg_id,
                message.get("response_url") or "",
                "当前仅支持文本消息",
            )
            return HttpResponse("success", content_type="text/plain")

        clean_text = self.clean_text_message((message.get("text") or {}).get("content") or "")
        flow_input = self.build_flow_input(
            bot_id=self.channel_id,
            node_id="",
            message=message,
            clean_text=clean_text,
        )
        task_config = {**config, "response_url": message.get("response_url") or ""}
        from apps.opspilot.tasks import process_skill_channel_aibot_message

        process_skill_channel_aibot_message.delay(
            channel_id=self.channel_id,
            msg_id=msg_id,
            message=flow_input,
            sender_id=flow_input.get("user_id", ""),
            config=task_config,
        )
        return HttpResponse("success", content_type="text/plain")
