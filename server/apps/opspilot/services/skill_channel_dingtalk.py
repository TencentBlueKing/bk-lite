"""智能体钉钉 HTTP 回调渠道：复用 Bot 钉钉协议，执行单 Agent（不含 Stream 常驻客户端）。"""

from __future__ import annotations

import json
from typing import Any

from django.http import HttpRequest, HttpResponse, JsonResponse

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.enum import SkillChannelChoices
from apps.opspilot.models import SkillChannel
from apps.opspilot.services.dingtalk_chat_flow_utils import DingTalkChatFlowUtils

REQUIRED_DINGTALK_CONFIG_KEYS = ("client_id", "client_secret")


def normalize_dingtalk_channel_config(config: dict[str, Any] | None) -> dict[str, Any]:
    config = dict(config or {})
    out = dict(config)
    if not out.get("client_id") and config.get("appKey"):
        out["client_id"] = config["appKey"]
    if not out.get("client_secret") and config.get("appSecret"):
        out["client_secret"] = config["appSecret"]
    return out


def validate_dingtalk_channel_config(config: dict[str, Any]) -> list[str]:
    return [k for k in REQUIRED_DINGTALK_CONFIG_KEYS if not config.get(k)]


class SkillChannelDingtalkUtils(DingTalkChatFlowUtils):
    channel_name = "智能体钉钉"
    channel_code = "dingtalk"
    cache_key_prefix = "skill_channel_dingtalk_msg"

    def __init__(self, channel_id: int):
        super().__init__(channel_id)
        self.channel_id = channel_id

    def handle_request(self, request: HttpRequest) -> HttpResponse:
        channel = SkillChannel.objects.filter(
            id=self.channel_id,
            channel_type=SkillChannelChoices.DINGTALK,
        ).first()
        if not channel or not channel.enabled:
            if request.method == "GET":
                return HttpResponse("fail", status=403)
            return JsonResponse({"result": False, "message": "渠道不存在或已下线"}, status=403)

        config = normalize_dingtalk_channel_config(channel.channel_config)
        missing = validate_dingtalk_channel_config(config)
        if missing:
            logger.warning(
                "智能体钉钉配置缺失 channel_id=%s missing=%s",
                self.channel_id,
                ",".join(missing),
            )
            if request.method == "GET":
                return HttpResponse("fail", status=400)
            return JsonResponse({"success": False, "message": f"Missing config: {', '.join(missing)}"})

        if request.method == "GET":
            return HttpResponse("success")
        if request.method == "POST":
            return self.handle_skill_dingtalk_message(request, config)
        return HttpResponse("method not allowed", status=405)

    def handle_skill_dingtalk_message(self, request: HttpRequest, dingtalk_config: dict[str, Any]) -> JsonResponse:
        try:
            data = json.loads(request.body or b"{}")
            timestamp = request.headers.get("timestamp") or request.META.get("HTTP_TIMESTAMP")
            sign = request.headers.get("sign") or request.META.get("HTTP_SIGN")
            if timestamp and sign:
                if not self.verify_signature(timestamp, sign, dingtalk_config["client_secret"]):
                    logger.error("智能体钉钉签名验证失败 channel_id=%s", self.channel_id)
                    return JsonResponse({"success": False, "message": "Invalid signature"})

            msg_type = data.get("msgtype")
            if msg_type != "text":
                logger.info(
                    "智能体钉钉忽略非文本消息 channel_id=%s type=%s",
                    self.channel_id,
                    msg_type,
                )
                return JsonResponse({"success": True})

            text_content = (data.get("text") or {}).get("content", "") or ""
            sender_id = data.get("senderStaffId", "") or data.get("senderId", "")
            msg_id = data.get("msgId", "") or f"{sender_id}:{hash(text_content)}:{timestamp or ''}"
            webhook_url = data.get("sessionWebhook") or ""

            if not text_content:
                return JsonResponse({"success": True})
            if self.is_message_processed(msg_id):
                return JsonResponse({"success": True})

            from apps.opspilot.tasks import process_skill_channel_dingtalk_message

            process_skill_channel_dingtalk_message.delay(
                channel_id=self.channel_id,
                msg_id=msg_id,
                text_content=text_content,
                sender_id=sender_id,
                webhook_url=webhook_url,
                config=dingtalk_config,
            )
            return JsonResponse({"success": True})
        except Exception as e:
            logger.exception("智能体钉钉消息处理失败 channel_id=%s", self.channel_id)
            return JsonResponse({"success": False, "message": str(e)})
