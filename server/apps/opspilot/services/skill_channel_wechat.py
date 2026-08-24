"""智能体企微应用渠道：复用 Bot 企微协议，执行单 Agent。"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest, HttpResponse, JsonResponse
from wechatpy.enterprise.crypto import WeChatCrypto

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.enum import SkillChannelChoices
from apps.opspilot.models import SkillChannel
from apps.opspilot.utils.wechat_chat_flow_utils import WechatChatFlowUtils

REQUIRED_WECHAT_CONFIG_KEYS = ("token", "aes_key", "corp_id", "agent_id", "secret")


def normalize_wechat_channel_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """将 SkillChannel.channel_config 规范为 Bot 企微应用节点字段。"""
    config = dict(config or {})
    out = dict(config)
    if not out.get("aes_key") and (config.get("encodingAESKey") or config.get("aesKey")):
        out["aes_key"] = config.get("encodingAESKey") or config.get("aesKey")
    return out


def validate_wechat_channel_config(config: dict[str, Any]) -> list[str]:
    return [k for k in REQUIRED_WECHAT_CONFIG_KEYS if not config.get(k)]


class SkillChannelWechatUtils(WechatChatFlowUtils):
    """去重键使用 channel_id；协议方法继承自 Bot 企微 utils。"""

    channel_name = "智能体企微应用"
    channel_code = "enterprise_wechat"
    cache_key_prefix = "skill_channel_wechat_msg"

    def __init__(self, channel_id: int):
        super().__init__(channel_id)
        self.channel_id = channel_id

    def handle_request(self, request: HttpRequest) -> HttpResponse:
        channel = SkillChannel.objects.filter(
            id=self.channel_id,
            channel_type=SkillChannelChoices.ENTERPRISE_WECHAT,
        ).first()
        if not channel or not channel.enabled:
            if request.method == "GET":
                return HttpResponse("fail", status=403)
            return JsonResponse({"result": False, "message": "渠道不存在或已下线"}, status=403)

        config = normalize_wechat_channel_config(channel.channel_config)
        missing = validate_wechat_channel_config(config)
        if missing:
            logger.warning(
                "智能体企微应用配置缺失 channel_id=%s missing=%s",
                self.channel_id,
                ",".join(missing),
            )
            return HttpResponse("fail" if request.method == "GET" else "success")

        try:
            crypto = WeChatCrypto(config["token"], config["aes_key"], config["corp_id"])
        except Exception:
            logger.exception("智能体企微应用创建加密对象失败 channel_id=%s", self.channel_id)
            return HttpResponse("fail" if request.method == "GET" else "success")

        if request.method == "GET":
            return self.handle_url_verification(
                crypto,
                request.GET.get("signature", "") or request.GET.get("msg_signature", ""),
                request.GET.get("timestamp", ""),
                request.GET.get("nonce", ""),
                request.GET.get("echostr", ""),
            )
        if request.method == "POST":
            return self.handle_skill_wechat_message(request, crypto, config)
        return HttpResponse("method not allowed", status=405)

    def handle_skill_wechat_message(self, request: HttpRequest, crypto: WeChatCrypto, wechat_config: dict[str, Any]) -> HttpResponse:
        signature = request.GET.get("signature", "") or request.GET.get("msg_signature", "")
        timestamp = request.GET.get("timestamp", "")
        nonce = request.GET.get("nonce", "")
        if not signature or not timestamp or not nonce:
            logger.error("智能体企微应用消息缺少签名参数 channel_id=%s", self.channel_id)
            return HttpResponse("success")

        try:
            decrypted_xml = crypto.decrypt_message(request.body, signature, timestamp, nonce)
            msg = self.parse_message(decrypted_xml)
            if not msg or getattr(msg, "type", None) != "text":
                logger.info(
                    "智能体企微应用忽略非文本消息 channel_id=%s type=%s",
                    self.channel_id,
                    getattr(msg, "type", None),
                )
                return HttpResponse("success")

            message = getattr(msg, "content", "") or ""
            sender_id = getattr(msg, "source", "") or ""
            msg_id = getattr(msg, "id", "") or f"{sender_id}:{hash(message)}:{timestamp}"
            if not message:
                return HttpResponse("success")

            if self.is_message_processed(msg_id):
                return HttpResponse("success")

            from apps.opspilot.tasks import process_skill_channel_wechat_message

            process_skill_channel_wechat_message.delay(
                channel_id=self.channel_id,
                msg_id=msg_id,
                message=message,
                sender_id=sender_id,
                config=wechat_config,
            )
            return HttpResponse("success")
        except Exception:
            logger.exception("智能体企微应用消息处理失败 channel_id=%s", self.channel_id)
            return HttpResponse("success")
