"""智能体飞书事件订阅回调。"""

import base64
import hashlib
import json

import pytest
from Crypto.Cipher import AES
from rest_framework.test import APIRequestFactory

from apps.opspilot import views as opspilot_views
from apps.opspilot.enum import SkillChannelChoices
from apps.opspilot.models import LLMSkill, SkillChannel
from apps.opspilot.services.skill_channel_feishu import decrypt_feishu_payload

pytestmark = pytest.mark.django_db

APP_ID = "cli_test"
APP_SECRET = "secret-value"
VERIFY_TOKEN = "verify-token"
ENCRYPT_KEY = "encrypt-key"


def _skill():
    return LLMSkill.objects.create(name="feishu-skill", team=[1], usage_team=[1])


def _channel(**config):
    merged = {
        "app_id": APP_ID,
        "app_secret": APP_SECRET,
        "verification_token": VERIFY_TOKEN,
    }
    merged.update(config)
    return SkillChannel.objects.create(
        skill=_skill(),
        channel_type=SkillChannelChoices.FEISHU,
        name="飞书",
        enabled=True,
        channel_config=merged,
        usage_team=[1],
    )


def _encrypt(key: str, payload: dict) -> str:
    raw_key = hashlib.sha256(key.encode("utf-8")).digest()
    iv = b"0123456789abcdef"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    pad = 16 - (len(data) % 16)
    data += bytes([pad]) * pad
    cipher = AES.new(raw_key, AES.MODE_CBC, iv)
    return base64.b64encode(iv + cipher.encrypt(data)).decode("utf-8")


def _post(channel, body: dict, *, encrypt_key: str = "", headers: dict | None = None):
    raw = json.dumps(body).encode("utf-8")
    extra = {}
    if encrypt_key:
        timestamp = "1710000000"
        nonce = "nonce"
        signature = hashlib.sha256((timestamp + nonce + encrypt_key).encode("utf-8") + raw).hexdigest()
        extra = {
            "HTTP_X_LARK_SIGNATURE": signature,
            "HTTP_X_LARK_REQUEST_TIMESTAMP": timestamp,
            "HTTP_X_LARK_REQUEST_NONCE": nonce,
        }
    if headers:
        extra.update(headers)
    request = APIRequestFactory().post("/", data=raw, content_type="application/json", **extra)
    return opspilot_views.execute_skill_channel_im(
        request,
        channel_id=channel.id,
        channel_type=SkillChannelChoices.FEISHU,
    )


def test_url_verification_returns_challenge():
    channel = _channel()
    response = _post(
        channel,
        {"type": "url_verification", "challenge": "challenge-1", "token": VERIFY_TOKEN},
    )
    assert response.status_code == 200
    assert json.loads(response.content) == {"challenge": "challenge-1"}


def test_rejects_mismatched_verification_token():
    channel = _channel()
    response = _post(
        channel,
        {"type": "url_verification", "challenge": "challenge-1", "token": "other"},
    )
    assert response.status_code == 403


def test_encrypted_url_verification():
    """飞书网址校验：有 Encrypt Key 时只发 encrypt，通常不带签名头。"""
    channel = _channel(encrypt_key=ENCRYPT_KEY)
    encrypted = _encrypt(
        ENCRYPT_KEY,
        {"type": "url_verification", "challenge": "challenge-enc", "token": VERIFY_TOKEN},
    )
    assert json.loads(decrypt_feishu_payload(ENCRYPT_KEY, encrypted))["challenge"] == "challenge-enc"
    # 不带 X-Lark-Signature，模拟飞书真实握手
    response = _post(channel, {"encrypt": encrypted})
    assert response.status_code == 200
    assert json.loads(response.content) == {"challenge": "challenge-enc"}


def test_encrypted_url_verification_with_signature_still_works():
    channel = _channel(encrypt_key=ENCRYPT_KEY)
    encrypted = _encrypt(
        ENCRYPT_KEY,
        {"type": "url_verification", "challenge": "challenge-sig", "token": VERIFY_TOKEN},
    )
    response = _post(channel, {"encrypt": encrypted}, encrypt_key=ENCRYPT_KEY)
    assert response.status_code == 200
    assert json.loads(response.content) == {"challenge": "challenge-sig"}


def test_encrypted_event_without_signature_is_rejected(monkeypatch):
    channel = _channel(encrypt_key=ENCRYPT_KEY)
    monkeypatch.setattr(
        "apps.opspilot.tasks.process_skill_channel_feishu_message.delay",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not queue")),
    )
    encrypted = _encrypt(
        ENCRYPT_KEY,
        {
            "schema": "2.0",
            "header": {
                "event_type": "im.message.receive_v1",
                "token": VERIFY_TOKEN,
                "app_id": APP_ID,
            },
            "event": {
                "sender": {"sender_type": "user", "sender_id": {"open_id": "ou_1"}},
                "message": {
                    "message_id": "om_nosig",
                    "message_type": "text",
                    "content": json.dumps({"text": "hi"}),
                },
            },
        },
    )
    response = _post(channel, {"encrypt": encrypted})
    assert response.status_code == 403
    assert json.loads(response.content)["message"] == "飞书签名校验失败"


def test_text_event_is_queued(monkeypatch):
    channel = _channel()
    queued = {}

    def _delay(**kwargs):
        queued.update(kwargs)

    monkeypatch.setattr(
        "apps.opspilot.tasks.process_skill_channel_feishu_message.delay",
        _delay,
    )
    response = _post(
        channel,
        {
            "schema": "2.0",
            "header": {
                "event_type": "im.message.receive_v1",
                "token": VERIFY_TOKEN,
                "app_id": APP_ID,
                "event_id": "evt-1",
            },
            "event": {
                "sender": {"sender_type": "user", "sender_id": {"open_id": "ou_1"}},
                "message": {
                    "message_id": "om_1",
                    "message_type": "text",
                    "content": json.dumps({"text": "你好"}),
                },
            },
        },
    )
    assert response.status_code == 200
    assert queued["channel_id"] == channel.id
    assert queued["msg_id"] == "om_1"
    assert queued["text_content"] == "你好"
    assert queued["sender_id"] == "ou_1"


def test_ignores_bot_sender(monkeypatch):
    channel = _channel()
    called = {"n": 0}

    def _delay(**kwargs):
        called["n"] += 1

    monkeypatch.setattr(
        "apps.opspilot.tasks.process_skill_channel_feishu_message.delay",
        _delay,
    )
    response = _post(
        channel,
        {
            "header": {
                "event_type": "im.message.receive_v1",
                "token": VERIFY_TOKEN,
                "app_id": APP_ID,
            },
            "event": {
                "sender": {"sender_type": "bot", "sender_id": {"open_id": "ou_bot"}},
                "message": {
                    "message_id": "om_bot",
                    "message_type": "text",
                    "content": json.dumps({"text": "echo"}),
                },
            },
        },
    )
    assert response.status_code == 200
    assert called["n"] == 0


def test_disabled_channel_still_answers_url_verification():
    channel = _channel()
    channel.enabled = False
    channel.save(update_fields=["enabled"])
    response = _post(
        channel,
        {"type": "url_verification", "challenge": "c", "token": VERIFY_TOKEN},
    )
    assert response.status_code == 200
    assert json.loads(response.content) == {"challenge": "c"}


def test_disabled_channel_rejects_message_events(monkeypatch):
    channel = _channel()
    channel.enabled = False
    channel.save(update_fields=["enabled"])
    monkeypatch.setattr(
        "apps.opspilot.tasks.process_skill_channel_feishu_message.delay",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not queue")),
    )
    response = _post(
        channel,
        {
            "schema": "2.0",
            "header": {"event_type": "im.message.receive_v1", "token": VERIFY_TOKEN, "app_id": APP_ID},
            "event": {
                "sender": {"sender_type": "user", "sender_id": {"open_id": "ou_1"}},
                "message": {
                    "message_id": "om_disabled",
                    "message_type": "text",
                    "content": json.dumps({"text": "hi"}),
                },
            },
        },
    )
    assert response.status_code == 403
