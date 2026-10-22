"""智能体企微智能机器人（aibot）渠道：复用 Bot 协议，执行单 Agent。"""

from __future__ import annotations

import os
from typing import Any

from django.http import HttpRequest, HttpResponse, JsonResponse

from apps.core.logger import opspilot_logger as logger
from apps.core.logger import safe_log_value
from apps.opspilot.enum import SkillChannelChoices
from apps.opspilot.models import SkillChannel, WorkflowAttachmentAsset
from apps.opspilot.services.workflow_attachment_service import build_server_attachment_download_path
from apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils import EnterpriseWechatAibotChatFlowUtils
from apps.opspilot.utils.enterprise_wechat_aibot_crypto import EnterpriseWechatAibotCrypto, EnterpriseWechatAibotCryptoError

SHORT_CONNECTION_FILE_LINKED_LOG = "event=wecom_aibot_short_connection_file_linked channel_id=%s file_count=%s"
SHORT_CONNECTION_FILE_SKIPPED_LOG = "event=wecom_aibot_short_connection_file_skipped channel_id=%s failed_stage=download_origin file_count=%s"
DOWNLOAD_PUBLIC_BASE_URL_ENV = "WECOM_AIBOT_PUBLIC_BASE_URL"

SKILL_CHANNEL_AIBOT_DECRYPT_FAILED_TEMPLATE = (
    "event=skill_channel_aibot_decrypt_failed channel_id=%s failed_stage=decrypt_callback "
    "error_type=%s has_msg_signature=%s has_timestamp=%s has_nonce=%s token_len=%s"
)


def _markdown_link_label(filename: str) -> str:
    label = (filename or "").replace("[", "").replace("]", "").replace("(", "").replace(")", "").strip()
    return label or "文件"


def callback_download_origin(request: HttpRequest) -> str:
    """企微回调已经打到的这台 server。下载链接用同一地址，不再另配站点。"""
    origin = request.build_absolute_uri("/").rstrip("/")
    if origin.startswith("http://") or origin.startswith("https://"):
        return origin
    return ""


def resolve_download_origin(request: HttpRequest, config: dict[str, Any] | None) -> str:
    """短连接下载外链优先用渠道/环境配置的公网地址，否则回退到本次回调 Host。"""
    config = config or {}
    webhook = config.get("webhook")
    if isinstance(webhook, dict):
        configured = webhook.get("publicBaseUrl") or webhook.get("downloadPublicBaseUrl") or ""
        if isinstance(configured, str):
            base = configured.strip().rstrip("/")
            if base.startswith("http://") or base.startswith("https://"):
                return base
    env_base = (os.environ.get(DOWNLOAD_PUBLIC_BASE_URL_ENV) or "").strip().rstrip("/")
    if env_base.startswith("http://") or env_base.startswith("https://"):
        return env_base
    return callback_download_origin(request)


def append_short_connection_file_links(content: str, execution_id: str, channel_id: int, *, origin: str) -> str:
    """短连接只能回 Markdown。链接指向后台接口，由 server 从 MinIO 读出文件。"""
    assets = list(WorkflowAttachmentAsset.objects.filter(execution_id=execution_id).order_by("id"))
    if not assets:
        return content
    base = (origin or "").rstrip("/")
    if not (base.startswith("http://") or base.startswith("https://")):
        logger.warning(SHORT_CONNECTION_FILE_SKIPPED_LOG, channel_id, len(assets))
        return content
    lines = []
    body = content or ""
    for asset in assets:
        path = build_server_attachment_download_path(asset)
        if path in body:
            continue
        lines.append(f"[{_markdown_link_label(asset.filename)}]({base}{path})")
    if not lines:
        return content
    logger.info(SHORT_CONNECTION_FILE_LINKED_LOG, channel_id, len(lines))
    block = "\n".join(lines)
    stripped = body.rstrip()
    if not stripped:
        return block
    return f"{stripped}\n\n{block}"


def normalize_aibot_channel_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """保留渠道上已选择的连接方式；缺省仍是短连接 webhook。"""
    config = dict(config or {})
    if config.get("connectionMode") == "websocket" or (config.get("websocket") and config.get("connectionMode") != "webhook"):
        out = dict(config)
        out["connectionMode"] = "websocket"
        websocket = dict(out.get("websocket") or {})
        bot_id = websocket.get("botId")
        secret = websocket.get("secret")
        if isinstance(bot_id, str):
            websocket["botId"] = bot_id.strip()
        if isinstance(secret, str):
            websocket["secret"] = secret.strip()
        out["websocket"] = websocket
        return out
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
        task_config = {
            **config,
            "response_url": message.get("response_url") or "",
            "download_origin": resolve_download_origin(request, config),
        }
        from apps.opspilot.tasks import process_skill_channel_aibot_message

        process_skill_channel_aibot_message.delay(
            channel_id=self.channel_id,
            msg_id=msg_id,
            message=flow_input,
            sender_id=flow_input.get("user_id", ""),
            config=task_config,
        )
        return HttpResponse("success", content_type="text/plain")
