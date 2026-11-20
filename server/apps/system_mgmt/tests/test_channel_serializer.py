from types import SimpleNamespace

import pytest
from django.test import RequestFactory

from apps.system_mgmt.models import Channel, ChannelChoices
from apps.system_mgmt.serializers import ChannelSerializer


def _request_with_locale(locale):
    request = RequestFactory().post("/system_mgmt/api/")
    request.user = SimpleNamespace(locale=locale)
    return request


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        ("en", "notification topic identifier is already in use"),
        ("zh-Hans", "通知主题标识已被使用"),
    ],
)
def test_event_publish_channel_rejects_duplicate_subject_key(locale, expected):
    Channel.objects.create(
        name="existing-event-publish",
        channel_type=ChannelChoices.NATS,
        description="Existing event publish channel",
        team=[],
        config={"nats_mode": "event_publish", "subject_key": "customer-alerts"},
    )

    serializer = ChannelSerializer(
        data={
            "name": "duplicate-event-publish",
            "channel_type": ChannelChoices.NATS,
            "description": "Duplicate event publish channel",
            "team": [],
            "config": {"nats_mode": "event_publish", "subject_key": "customer-alerts"},
        },
        context={"request": _request_with_locale(locale)},
    )

    assert serializer.is_valid() is False
    assert serializer.errors["config"]["subject_key"] == expected


@pytest.mark.django_db
def test_event_publish_channel_allows_its_own_subject_key_when_editing():
    channel = Channel.objects.create(
        name="existing-event-publish",
        channel_type=ChannelChoices.NATS,
        description="Existing event publish channel",
        team=[],
        config={"nats_mode": "event_publish", "subject_key": "customer-alerts"},
    )

    serializer = ChannelSerializer(
        channel,
        data={
            "name": channel.name,
            "channel_type": ChannelChoices.NATS,
            "description": channel.description,
            "team": channel.team,
            "config": {"nats_mode": "event_publish", "subject_key": "customer-alerts"},
        },
    )

    assert serializer.is_valid() is True


@pytest.mark.django_db
def test_nats_channel_rejects_non_boolean_notify_person_flag():
    serializer = ChannelSerializer(
        data={
            "name": "invalid-notify-person",
            "channel_type": ChannelChoices.NATS,
            "description": "Invalid config",
            "team": [],
            "config": {"supports_notify_person": "true"},
        }
    )

    assert serializer.is_valid() is False
    assert "supports_notify_person" in str(serializer.errors)


def _sms_payload(**config):
    body = {
        "provider": "tencent",
        "secret_id": "AKIDexample",
        "secret_key": "cloud-secret-key",
        "sdk_app_id": "1400006666",
        "sign_name": "运维平台",
        "template_id": "100001",
        "parameters": [{"source": "content", "name": "", "value": ""}],
    }
    body.update(config)
    return {
        "name": "短信",
        "channel_type": ChannelChoices.SMS,
        "description": "告警短信",
        "team": [1],
        "config": body,
    }


@pytest.mark.django_db
def test_sms_channel_masks_secret_and_keeps_it_when_mask_is_submitted():
    created = ChannelSerializer(data=_sms_payload())
    assert created.is_valid(), created.errors
    channel = created.save()

    assert channel.config["secret_key"] != "cloud-secret-key"
    plain = dict(channel.config)
    Channel.decrypt_field("secret_key", plain)
    assert plain["secret_key"] == "cloud-secret-key"

    shown = ChannelSerializer(channel).data["config"]["secret_key"]
    assert shown == "******-key"
    assert "cloud-secret" not in shown

    payload = _sms_payload()
    payload["config"]["secret_key"] = shown
    payload["config"]["sign_name"] = "新签名"
    updated = ChannelSerializer(channel, data=payload)
    assert updated.is_valid(), updated.errors
    saved = updated.save()
    decrypted = dict(saved.config)
    Channel.decrypt_field("secret_key", decrypted)
    assert decrypted["secret_key"] == "cloud-secret-key"
    assert decrypted["sign_name"] == "新签名"


@pytest.mark.django_db
def test_sms_channel_keeps_secret_when_update_submits_empty_value():
    created = ChannelSerializer(data=_sms_payload())
    assert created.is_valid(), created.errors
    channel = created.save()

    payload = _sms_payload()
    payload["config"]["secret_id"] = ""
    payload["config"]["secret_key"] = ""
    payload["config"]["sign_name"] = "新签名"
    updated = ChannelSerializer(channel, data=payload)
    assert updated.is_valid(), updated.errors
    saved = updated.save()
    decrypted = dict(saved.config)
    Channel.decrypt_field("secret_id", decrypted)
    Channel.decrypt_field("secret_key", decrypted)
    assert decrypted["secret_id"] == "AKIDexample"
    assert decrypted["secret_key"] == "cloud-secret-key"
    assert decrypted["sign_name"] == "新签名"

    empty_create = ChannelSerializer(data=_sms_payload(secret_key=""))
    assert empty_create.is_valid() is False
    assert "secret_key" in empty_create.errors["config"]


@pytest.mark.django_db
def test_sms_channel_rejects_missing_template_id_and_unknown_provider():
    missing = ChannelSerializer(data=_sms_payload(template_id=""))
    assert missing.is_valid() is False
    assert missing.errors["config"]["template_id"] == "This field is required"

    voice = {
        "name": "语音",
        "channel_type": ChannelChoices.VOICE,
        "description": "告警语音",
        "team": [1],
        "config": {
            "provider": "aliyun",
            "access_key_id": "LTAIexample",
            "access_key_secret": "cloud-secret-key",
            "template_code": "   ",
        },
    }
    missing_code = ChannelSerializer(data=voice)
    assert missing_code.is_valid() is False
    assert missing_code.errors["config"]["template_code"] == "This field is required"

    unknown = ChannelSerializer(data=_sms_payload(provider="other"))
    assert unknown.is_valid() is False
    assert unknown.errors["config"]["provider"] == "The cloud provider must be Tencent Cloud or Alibaba Cloud"


@pytest.mark.django_db
def test_sms_channel_stores_aliyun_names_and_rejects_duplicates():
    payload = _sms_payload(
        provider="aliyun",
        access_key_id="LTAIexample",
        access_key_secret="cloud-secret-key",
        template_code="SMS_1",
        parameters=[{"source": "content", "name": " scene ", "value": "旧值", "test_value": " 磁盘 "}, {"name": "level"}],
    )
    payload["config"].pop("secret_id", None)
    payload["config"].pop("secret_key", None)
    payload["config"].pop("sdk_app_id", None)
    payload["config"].pop("template_id", None)
    created = ChannelSerializer(data=payload)
    assert created.is_valid(), created.errors
    channel = created.save()
    assert channel.config["parameters"] == [{"name": "scene", "test_value": "磁盘"}, {"name": "level", "test_value": ""}]

    payload["config"]["parameters"] = [{"name": "scene"}, {"name": "scene"}]
    duplicated = ChannelSerializer(data=payload)
    assert duplicated.is_valid() is False
    assert "parameters.1" in duplicated.errors["config"]


@pytest.mark.django_db
def test_sms_channel_stores_tencent_test_values_and_rejects_non_strings():
    payload = _sms_payload(parameters=[{"name": "ignored", "test_value": " 磁盘 "}, {"test_value": ""}])
    created = ChannelSerializer(data=payload)
    assert created.is_valid(), created.errors
    channel = created.save()
    assert channel.config["parameters"] == [{"name": "", "test_value": "磁盘"}, {"name": "", "test_value": ""}]

    payload["config"]["parameters"] = [{"name": "", "test_value": 1}]
    rejected = ChannelSerializer(data=payload)
    assert rejected.is_valid() is False
    assert rejected.errors["config"]["parameters.0"] == "A test value must be a string"


@pytest.mark.django_db
def test_sms_channel_rejects_more_than_twenty_template_parameters():
    serializer = ChannelSerializer(data=_sms_payload(parameters=[{"source": "title", "name": "", "value": ""} for _ in range(21)]))
    assert serializer.is_valid() is False
    assert "parameters" in serializer.errors["config"]
