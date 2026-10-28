"""智能体企微智能机器人（aibot）渠道：复用 Bot 协议，执行单 Agent。"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any

from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, JsonResponse

from apps.core.logger import opspilot_logger as logger
from apps.core.logger import safe_log_value
from apps.opspilot.enum import SkillChannelChoices
from apps.opspilot.models import SkillChannel, WorkflowAttachmentAsset
from apps.opspilot.services.skill_channel_im_media import wecom_short_connection_outbound
from apps.opspilot.services.workflow_attachment_service import build_server_attachment_download_path
from apps.opspilot.utils.enterprise_wechat_aibot_chat_flow_utils import EnterpriseWechatAibotChatFlowUtils
from apps.opspilot.utils.enterprise_wechat_aibot_crypto import EnterpriseWechatAibotCrypto, EnterpriseWechatAibotCryptoError

SHORT_CONNECTION_FILE_LINKED_LOG = "event=wecom_aibot_short_connection_file_linked channel_id=%s file_count=%s"
SHORT_CONNECTION_FILE_SKIPPED_LOG = "event=wecom_aibot_short_connection_file_skipped channel_id=%s failed_stage=download_origin file_count=%s"
SHORT_CONNECTION_IMAGE_REPLY_LOG = "event=wecom_aibot_short_connection_image_reply channel_id=%s image_count=%s"
DOWNLOAD_PUBLIC_BASE_URL_ENV = "WECOM_AIBOT_PUBLIC_BASE_URL"
SHORT_CONNECTION_PROCESSING_TEXT = "正在处理"
SHORT_CONNECTION_STREAM_CACHE_SECONDS = 7200
SHORT_CONNECTION_STREAM_FALLBACK_SECONDS = 20
_STREAM_KEY = "skill_channel_aibot_stream:{channel_id}:{stream_id}"
_STREAM_CLAIM_KEY = "skill_channel_aibot_stream_claim:{channel_id}:{stream_id}"
_STREAM_IMAGE_KEY = "skill_channel_aibot_stream_image:{channel_id}:{stream_id}"
_DELIVERY_CLAIM_SECONDS = 30

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


def _stream_cache_key(channel_id: int, stream_id: str) -> str:
    return _STREAM_KEY.format(channel_id=channel_id, stream_id=stream_id)


def open_short_connection_stream(channel_id: int, stream_id: str, response_url: str) -> None:
    cache.set(
        _stream_cache_key(channel_id, stream_id),
        {"phase": "processing", "reply_text": "", "delivered": False, "response_url": response_url or ""},
        SHORT_CONNECTION_STREAM_CACHE_SECONDS,
    )


def finish_short_connection_stream(
    channel_id: int,
    stream_id: str,
    reply_text: str,
    *,
    visible: str | None = None,
    msg_items: list[dict] | None = None,
) -> None:
    """写入完成态。图片在这里物化进缓存，轮询不再下载。"""
    if visible is None or msg_items is None:
        materialized_visible, materialized_items = wecom_short_connection_outbound(reply_text or "")
        if visible is None:
            visible = materialized_visible
        if msg_items is None:
            msg_items = materialized_items
    key = _stream_cache_key(channel_id, stream_id)
    state = dict(cache.get(key) or {})
    state["phase"] = "finished"
    state["reply_text"] = reply_text or ""
    state["visible"] = visible or ""
    state["msg_items"] = list(msg_items or [])
    state.setdefault("delivered", False)
    state.setdefault("stream_committed", False)
    state.setdefault("text_delivered", False)
    state.setdefault("images_delivered", False)
    cache.set(key, state, SHORT_CONNECTION_STREAM_CACHE_SECONDS)


def _image_claim_key(channel_id: int, stream_id: str) -> str:
    return _STREAM_IMAGE_KEY.format(channel_id=channel_id, stream_id=stream_id)


def _text_claim_key(channel_id: int, stream_id: str) -> str:
    return _STREAM_CLAIM_KEY.format(channel_id=channel_id, stream_id=stream_id)


def release_short_connection_delivery(channel_id: int, stream_id: str) -> None:
    """放弃尚未加密成功的文本认领。已加密结束的流保持 stream_committed。"""
    key = _stream_cache_key(channel_id, stream_id)
    state = cache.get(key)
    if isinstance(state, dict):
        state = dict(state)
        if not state.get("stream_committed"):
            state["delivered"] = False
            state["text_delivered"] = False
            cache.set(key, state, SHORT_CONNECTION_STREAM_CACHE_SECONDS)
    cache.delete(_text_claim_key(channel_id, stream_id))


def claim_short_connection_delivery(channel_id: int, stream_id: str) -> bool:
    """补发 response_url 纯文本。不消耗已物化图片，轮询仍可把图片放进结束帧。"""
    key = _stream_cache_key(channel_id, stream_id)
    state = cache.get(key)
    if not isinstance(state, dict) or state.get("phase") != "finished":
        return False
    if state.get("stream_committed") or state.get("delivered") or state.get("text_delivered"):
        return False
    claim_key = _text_claim_key(channel_id, stream_id)
    if not cache.add(claim_key, "1", _DELIVERY_CLAIM_SECONDS):
        return False
    state = dict(cache.get(key) or {})
    if (
        state.get("phase") != "finished"
        or state.get("stream_committed")
        or state.get("delivered")
        or state.get("text_delivered")
    ):
        cache.delete(claim_key)
        return False
    state["text_delivered"] = True
    cache.set(key, state, SHORT_CONNECTION_STREAM_CACHE_SECONDS)
    return True


def commit_short_connection_stream_delivery(channel_id: int, stream_id: str, *, images_included: bool) -> None:
    """加密结束帧已经可以返回给企微，这时才挡住 response_url 补发。"""
    key = _stream_cache_key(channel_id, stream_id)
    state = cache.get(key)
    if not isinstance(state, dict):
        return
    state = dict(state)
    state["stream_committed"] = True
    state["delivered"] = True
    if images_included:
        state["images_delivered"] = True
    cache.set(key, state, SHORT_CONNECTION_STREAM_CACHE_SECONDS)
    if images_included:
        items = state.get("msg_items")
        logger.info(SHORT_CONNECTION_IMAGE_REPLY_LOG, channel_id, len(items) if isinstance(items, list) else 0)


def settle_short_connection_poll(
    channel_id: int,
    stream_id: str,
    *,
    encrypted: bool,
    finish: bool,
    images_included: bool,
) -> None:
    """结束帧只有加密成功才固化认领；失败则释放，让补发还能 claim。"""
    if not finish or not stream_id:
        return
    if encrypted:
        commit_short_connection_stream_delivery(channel_id, stream_id, images_included=images_included)
        return
    if images_included:
        cache.delete(_image_claim_key(channel_id, stream_id))
    state = cache.get(_stream_cache_key(channel_id, stream_id))
    text_delivered = isinstance(state, dict) and bool(state.get("text_delivered"))
    stream_committed = isinstance(state, dict) and bool(state.get("stream_committed"))
    if not stream_committed and not text_delivered:
        release_short_connection_delivery(channel_id, stream_id)


def short_connection_stream_payload(channel_id: int, stream_id: str) -> tuple[dict[str, Any], bool]:
    """企微流式刷新只读缓存。图片在 finish 时已经物化，这里不再下载。"""
    state = cache.get(_stream_cache_key(channel_id, stream_id))
    if not isinstance(state, dict):
        return {"msgtype": "stream", "stream": {"id": stream_id, "finish": True, "content": ""}}, False
    if state.get("phase") != "finished":
        return {
            "msgtype": "stream",
            "stream": {"id": stream_id, "finish": False, "content": SHORT_CONNECTION_PROCESSING_TEXT},
        }, False
    visible = state.get("visible")
    if not isinstance(visible, str):
        visible = ""
    items = state.get("msg_items")
    if not isinstance(items, list):
        items = []
    stream: dict[str, Any] = {"id": stream_id, "finish": True, "content": visible}
    images_included = False
    if items:
        # 没拿到图片认领就结束，企微会停轮询，慢的那帧或重试会把图丢掉。
        if not cache.add(_image_claim_key(channel_id, stream_id), "1", _DELIVERY_CLAIM_SECONDS):
            return {
                "msgtype": "stream",
                "stream": {"id": stream_id, "finish": False, "content": SHORT_CONNECTION_PROCESSING_TEXT},
            }, False
        stream["msg_item"] = items
        images_included = True
    return {"msgtype": "stream", "stream": stream}, images_included


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

        if message.get("msgtype") == "stream":
            stream_id = str((message.get("stream") or {}).get("id") or "").strip()
            payload, images_included = short_connection_stream_payload(self.channel_id, stream_id)
            response = self._encrypted_passive_reply(request, crypto, payload, self.channel_id)
            settle_short_connection_poll(
                self.channel_id,
                stream_id,
                encrypted=isinstance(response, JsonResponse),
                finish=bool((payload.get("stream") or {}).get("finish")),
                images_included=images_included,
            )
            return response

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
        response_url = message.get("response_url") or ""
        stream_id = uuid.uuid4().hex
        open_short_connection_stream(self.channel_id, stream_id, response_url)
        task_config = {
            **config,
            "response_url": response_url,
            "download_origin": resolve_download_origin(request, config),
            "stream_id": stream_id,
        }
        from apps.opspilot.tasks import process_skill_channel_aibot_message

        process_skill_channel_aibot_message.delay(
            channel_id=self.channel_id,
            msg_id=msg_id,
            message=flow_input,
            sender_id=flow_input.get("user_id", ""),
            config=task_config,
        )
        return self._encrypted_passive_reply(
            request,
            crypto,
            {
                "msgtype": "stream",
                "stream": {
                    "id": stream_id,
                    "finish": False,
                    "content": SHORT_CONNECTION_PROCESSING_TEXT,
                },
            },
            self.channel_id,
        )

    @staticmethod
    def _encrypted_passive_reply(
        request: HttpRequest,
        crypto: EnterpriseWechatAibotCrypto,
        payload: dict[str, Any],
        channel_id: int,
    ) -> HttpResponse:
        timestamp = (request.GET.get("timestamp") or "").strip() or str(int(time.time()))
        nonce = (request.GET.get("nonce") or "").strip() or uuid.uuid4().hex
        try:
            body = crypto.encrypt_reply(payload, timestamp=timestamp, nonce=nonce)
        except EnterpriseWechatAibotCryptoError:
            logger.warning(
                "event=wecom_aibot_short_connection_encrypt_failed channel_id=%s failed_stage=encrypt_reply error_type=%s",
                channel_id,
                "EnterpriseWechatAibotCryptoError",
            )
            return HttpResponse("success", content_type="text/plain")
        return JsonResponse(body)
