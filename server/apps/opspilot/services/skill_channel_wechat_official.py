"""智能体微信公众号渠道：复用 Bot 公众号协议，执行单 Agent。"""

from __future__ import annotations

from typing import Any

import xmltodict
from django.http import HttpRequest, HttpResponse, JsonResponse
from wechatpy import parse_message
from wechatpy.utils import to_text

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.enum import SkillChannelChoices
from apps.opspilot.models import SkillChannel
from apps.opspilot.services.wechat_official_chat_flow_utils import WechatOfficialChatFlowUtils

REQUIRED_OFFICIAL_CONFIG_KEYS = ("token", "appid", "secret", "aes_key")


def normalize_wechat_official_channel_config(config: dict[str, Any] | None) -> dict[str, Any]:
    config = dict(config or {})
    out = dict(config)
    if not out.get("aes_key") and (config.get("encodingAESKey") or config.get("aesKey")):
        out["aes_key"] = config.get("encodingAESKey") or config.get("aesKey")
    return out


def validate_wechat_official_channel_config(config: dict[str, Any]) -> list[str]:
    return [k for k in REQUIRED_OFFICIAL_CONFIG_KEYS if not config.get(k)]


class SkillChannelWechatOfficialUtils(WechatOfficialChatFlowUtils):
    channel_name = "智能体微信公众号"
    channel_code = "wechat_official"
    cache_key_prefix = "skill_channel_wechat_official_msg"

    def __init__(self, channel_id: int):
        super().__init__(channel_id)
        self.channel_id = channel_id

    def handle_request(self, request: HttpRequest) -> HttpResponse:
        channel = SkillChannel.objects.filter(
            id=self.channel_id,
            channel_type=SkillChannelChoices.WECHAT_OFFICIAL,
        ).first()
        if not channel or not channel.enabled:
            if request.method == "GET":
                return HttpResponse("fail", status=403)
            return JsonResponse({"result": False, "message": "渠道不存在或已下线"}, status=403)

        config = normalize_wechat_official_channel_config(channel.channel_config)
        missing = validate_wechat_official_channel_config(config)
        if missing:
            logger.warning(
                "智能体公众号配置缺失 channel_id=%s missing=%s",
                self.channel_id,
                ",".join(missing),
            )
            return HttpResponse("fail" if request.method == "GET" else "success")

        if request.method == "GET":
            return self.handle_url_verification(
                request.GET.get("signature", "") or request.GET.get("msg_signature", ""),
                request.GET.get("timestamp", ""),
                request.GET.get("nonce", ""),
                request.GET.get("echostr", ""),
                config["token"],
                config["aes_key"],
                config["appid"],
            )
        if request.method == "POST":
            return self.handle_skill_official_message(request, config)
        return HttpResponse("method not allowed", status=405)

    def handle_skill_official_message(self, request: HttpRequest, wechat_config: dict[str, Any]) -> HttpResponse:
        signature = request.GET.get("signature", "") or request.GET.get("msg_signature", "")
        timestamp = request.GET.get("timestamp", "")
        nonce = request.GET.get("nonce", "")
        if not signature or not timestamp or not nonce:
            logger.error("智能体公众号消息缺少签名参数 channel_id=%s", self.channel_id)
            return HttpResponse("success")

        try:
            xml_msg = xmltodict.parse(to_text(request.body))["xml"]
            decode_msg = self.decrypt(xml_msg["Encrypt"], wechat_config["aes_key"], wechat_config["appid"])
            msg = parse_message(decode_msg)
            if not msg or getattr(msg, "type", None) != "text":
                logger.info(
                    "智能体公众号忽略非文本消息 channel_id=%s type=%s",
                    self.channel_id,
                    getattr(msg, "type", None),
                )
                return HttpResponse("success")

            message = getattr(msg, "content", "") or ""
            openid = getattr(msg, "source", "") or ""
            msg_id = getattr(msg, "id", "") or f"{openid}:{hash(message)}:{timestamp}"
            if not message:
                return HttpResponse("success")
            if self.is_message_processed(msg_id):
                return HttpResponse("success")

            from apps.opspilot.tasks import process_skill_channel_wechat_official_message

            process_skill_channel_wechat_official_message.delay(
                channel_id=self.channel_id,
                msg_id=msg_id,
                message=message,
                sender_id=openid,
                config=wechat_config,
            )
            return HttpResponse("success")
        except Exception:
            logger.exception("智能体公众号消息处理失败 channel_id=%s", self.channel_id)
            return HttpResponse("success")
