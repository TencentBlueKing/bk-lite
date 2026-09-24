"""智能体飞书机器人渠道：事件订阅 HTTP 回调，单 Agent 回复。

参数对应飞书开放平台「凭证与基础信息」和「事件与回调 > 加密策略」：
- app_id / app_secret：换 tenant_access_token，并调用回复消息接口
- verification_token：校验 url_verification 与事件是否属于该应用
- encrypt_key：可选；配置后回调体为 encrypt，并用 X-Lark-Signature 验签
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any

import requests
from Crypto.Cipher import AES
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, JsonResponse

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.enum import SkillChannelChoices
from apps.opspilot.models import SkillChannel
from apps.opspilot.utils.base_chat_flow_utils import BaseChatFlowUtils

REQUIRED_FEISHU_CONFIG_KEYS = ("app_id", "app_secret", "verification_token")
FEISHU_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
FEISHU_REPLY_URL = "https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply"
FEISHU_TEXT_EVENT = "im.message.receive_v1"
_TOKEN_CACHE_PREFIX = "skill_channel_feishu_tat"


class FeishuChannelError(Exception):
    def __init__(self, message: str, status: int = 403):
        super().__init__(message)
        self.message = message
        self.status = status


def normalize_feishu_channel_config(config: dict[str, Any] | None) -> dict[str, Any]:
    config = dict(config or {})
    out = dict(config)
    if not out.get("app_id") and config.get("appId"):
        out["app_id"] = config["appId"]
    if not out.get("app_secret") and config.get("appSecret"):
        out["app_secret"] = config["appSecret"]
    if not out.get("verification_token") and config.get("verificationToken"):
        out["verification_token"] = config["verificationToken"]
    if not out.get("encrypt_key") and (config.get("encryptKey") or config.get("encodingAESKey")):
        out["encrypt_key"] = config.get("encryptKey") or config.get("encodingAESKey")
    for key in ("app_id", "app_secret", "verification_token", "encrypt_key"):
        if isinstance(out.get(key), str):
            out[key] = out[key].strip()
    return out


def validate_feishu_channel_config(config: dict[str, Any]) -> list[str]:
    return [key for key in REQUIRED_FEISHU_CONFIG_KEYS if not config.get(key)]


def decrypt_feishu_payload(encrypt_key: str, encrypt_text: str) -> str:
    """飞书 Encrypt Key：SHA256(key) 作 AES-256 密钥，密文前 16 字节为 IV。"""
    raw = base64.b64decode(encrypt_text)
    if len(raw) <= AES.block_size:
        raise FeishuChannelError("飞书回调解密失败", status=400)
    key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
    cipher = AES.new(key, AES.MODE_CBC, raw[: AES.block_size])
    padded = cipher.decrypt(raw[AES.block_size :])
    pad = padded[-1]
    if pad < 1 or pad > AES.block_size or padded[-pad:] != bytes([pad]) * pad:
        raise FeishuChannelError("飞书回调解密失败", status=400)
    return padded[:-pad].decode("utf-8")


def feishu_signature(timestamp: str, nonce: str, encrypt_key: str, body: bytes) -> str:
    seed = (timestamp + nonce + encrypt_key).encode("utf-8") + body
    return hashlib.sha256(seed).hexdigest()


class SkillChannelFeishuUtils(BaseChatFlowUtils):
    channel_name = "智能体飞书"
    channel_code = "feishu"
    cache_key_prefix = "skill_channel_feishu_msg"

    def __init__(self, channel_id: int):
        super().__init__(channel_id)
        self.channel_id = channel_id

    def send_reply(self, reply_text: str, sender_id: str, config: dict):
        message_id = (config or {}).get("message_id") or ""
        if not message_id or not reply_text:
            return
        token = self._tenant_access_token(config)
        response = requests.post(
            FEISHU_REPLY_URL.format(message_id=message_id),
            headers={"Authorization": f"Bearer {token}"},
            json={
                "msg_type": "text",
                "content": json.dumps({"text": reply_text}, ensure_ascii=False),
            },
            timeout=10,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise FeishuChannelError("飞书回复失败", status=502) from exc
        if response.status_code >= 400 or payload.get("code") not in (0, None):
            logger.warning(
                "智能体飞书回复失败 channel_id=%s message_id=%s status=%s code=%s",
                self.channel_id,
                message_id,
                response.status_code,
                payload.get("code"),
            )
            raise FeishuChannelError("飞书回复失败", status=502)

    def handle_request(self, request: HttpRequest) -> HttpResponse:
        if request.method != "POST":
            return HttpResponse("method not allowed", status=405)

        channel = SkillChannel.objects.filter(
            id=self.channel_id,
            channel_type=SkillChannelChoices.FEISHU,
        ).first()
        # URL 校验允许未启用：飞书保存回调地址时就会发 challenge，此时渠道常尚未上线。
        if not channel:
            return JsonResponse({"result": False, "message": "渠道不存在或已下线"}, status=403)

        config = normalize_feishu_channel_config(channel.channel_config)
        missing = validate_feishu_channel_config(config)
        if missing:
            logger.warning(
                "智能体飞书配置缺失 channel_id=%s missing=%s",
                self.channel_id,
                ",".join(missing),
            )
            return JsonResponse({"result": False, "message": f"Missing config: {', '.join(missing)}"}, status=400)

        try:
            payload = self._load_payload(request, config)
        except FeishuChannelError as exc:
            logger.warning(
                "智能体飞书回调校验失败 channel_id=%s status=%s error=%s",
                self.channel_id,
                exc.status,
                exc.message,
            )
            return JsonResponse({"result": False, "message": exc.message}, status=exc.status)

        if payload.get("type") == "url_verification":
            return JsonResponse({"challenge": payload.get("challenge", "")})

        if not channel.enabled:
            return JsonResponse({"result": False, "message": "渠道不存在或已下线"}, status=403)

        header = payload.get("header") or {}
        if header.get("event_type") != FEISHU_TEXT_EVENT:
            return JsonResponse({})

        event = payload.get("event") or {}
        sender = event.get("sender") or {}
        if sender.get("sender_type") == "bot":
            return JsonResponse({})
        message = event.get("message") or {}
        if message.get("message_type") not in (None, "", "text"):
            return JsonResponse({})

        text = _message_text(message.get("content"))
        message_id = message.get("message_id") or header.get("event_id") or ""
        sender_id = ((sender.get("sender_id") or {}).get("open_id")) or ""
        if not text or not message_id:
            return JsonResponse({})
        if self.is_message_processed(message_id):
            return JsonResponse({})

        # 任务模块反向依赖本服务，放在方法内避免 import cycle。
        from apps.opspilot.tasks import process_skill_channel_feishu_message

        process_skill_channel_feishu_message.delay(
            channel_id=self.channel_id,
            msg_id=message_id,
            text_content=text,
            sender_id=sender_id,
            config=config,
        )
        return JsonResponse({})

    def _load_payload(self, request: HttpRequest, config: dict[str, Any]) -> dict[str, Any]:
        try:
            body = json.loads(request.body or b"{}")
        except json.JSONDecodeError as exc:
            raise FeishuChannelError("飞书回调不是合法 JSON", status=400) from exc
        if not isinstance(body, dict):
            raise FeishuChannelError("飞书回调不是合法 JSON", status=400)

        encrypt_key = config.get("encrypt_key") or ""
        if encrypt_key:
            # 飞书「请求网址校验」在配置 Encrypt Key 时只发 encrypt 密文，
            # 官方说明该握手可不做签名校验，实际也不带 X-Lark-Signature；
            # 普通事件推送才会带签名头，必须验签。
            signature = request.headers.get("X-Lark-Signature") or ""
            timestamp = request.headers.get("X-Lark-Request-Timestamp") or ""
            nonce = request.headers.get("X-Lark-Request-Nonce") or ""
            if signature:
                expected = feishu_signature(timestamp, nonce, encrypt_key, request.body or b"")
                if not hmac.compare_digest(signature, expected):
                    raise FeishuChannelError("飞书签名校验失败")
            encrypt_text = body.get("encrypt")
            if not isinstance(encrypt_text, str) or not encrypt_text:
                raise FeishuChannelError("飞书回调缺少 encrypt", status=400)
            try:
                decrypted = decrypt_feishu_payload(encrypt_key, encrypt_text)
                body = json.loads(decrypted)
            except FeishuChannelError:
                raise
            except (json.JSONDecodeError, ValueError) as exc:
                raise FeishuChannelError("飞书回调解密失败", status=400) from exc
            if not isinstance(body, dict):
                raise FeishuChannelError("飞书回调解密失败", status=400)
            if body.get("type") != "url_verification" and not signature:
                raise FeishuChannelError("飞书签名校验失败")
        elif body.get("encrypt"):
            raise FeishuChannelError("飞书回调已加密，但渠道未配置 Encrypt Key", status=400)

        token = body.get("token") or (body.get("header") or {}).get("token") or ""
        if token != config["verification_token"]:
            raise FeishuChannelError("飞书 Verification Token 不匹配")
        header_app_id = (body.get("header") or {}).get("app_id")
        if header_app_id and header_app_id != config["app_id"]:
            raise FeishuChannelError("飞书 App ID 不匹配")
        return body

    def _tenant_access_token(self, config: dict[str, Any]) -> str:
        app_id = config["app_id"]
        cache_key = f"{_TOKEN_CACHE_PREFIX}:{app_id}"
        cached = cache.get(cache_key)
        if isinstance(cached, str) and cached:
            return cached
        response = requests.post(
            FEISHU_TOKEN_URL,
            json={"app_id": app_id, "app_secret": config["app_secret"]},
            timeout=10,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise FeishuChannelError("获取飞书访问凭证失败", status=502) from exc
        token = payload.get("tenant_access_token")
        if response.status_code >= 400 or payload.get("code") not in (0, None) or not token:
            logger.warning(
                "智能体飞书获取凭证失败 channel_id=%s status=%s code=%s",
                self.channel_id,
                response.status_code,
                payload.get("code"),
            )
            raise FeishuChannelError("获取飞书访问凭证失败", status=502)
        expire = int(payload.get("expire") or 7200)
        cache.set(cache_key, token, max(60, expire - 120))
        return token


def _message_text(content: Any) -> str:
    if isinstance(content, dict):
        return str(content.get("text") or "")
    if not isinstance(content, str) or not content:
        return ""
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return content
    if isinstance(parsed, dict):
        return str(parsed.get("text") or "")
    return content
