import logging
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.opspilot.enum import SkillChannelChoices
from apps.opspilot.models import LLMSkill, SkillChannel, SkillConversation
from apps.opspilot.serializers.skill_channel_serializer import SkillChannelSerializer
from apps.opspilot.services.skill_channel_account_association import SENDER_DENIED_TEXT, SENDER_NOT_EXECUTABLE_LOG, resolve_skill_channel_actor
from apps.opspilot.services.skill_channel_chat_service import execute_skill_channel_im_sync
from apps.system_mgmt.models import (
    IMAccountAssociation,
    IMNotificationSyncRun,
    IMNotificationSyncRunStatusChoices,
    IMNotificationUserMapping,
    IntegrationInstance,
    User,
)

pytestmark = pytest.mark.django_db

SENDER = "ou_lanyu"


@pytest.fixture
def super_client(db):
    from apps.base.models import User as BaseUser

    admin = BaseUser.objects.create_user(
        username="skill-channel-admin",
        password="pw",
        domain="domain.com",
        locale="en",
        email="skill-channel-admin@example.com",
    )
    admin.is_superuser = True
    admin.save()
    client = APIClient()
    client.force_authenticate(user=admin)
    return client


def _instance(name, provider_key, **config):
    return IntegrationInstance.objects.create(
        name=name,
        provider_key=provider_key,
        enabled=True,
        status="ready",
        capability_status={"im_notification": "ready"},
        config=config,
    )


def _association(name, instance, *, status="ready"):
    return IMAccountAssociation.objects.create(
        name=name,
        integration_instance=instance,
        platform_match_field="email",
        external_match_field="email",
        external_receive_field="user_id",
        status=status,
    )


def _user(**kwargs):
    defaults = dict(
        user_id=str(uuid.uuid4()),
        username=f"user-{uuid.uuid4().hex[:8]}",
        display_name="蓝羽",
        email="lanyu@example.com",
        password="",
        domain="domain.com",
        disabled=False,
        group_list=[{"id": 1, "name": "org"}],
    )
    defaults.update(kwargs)
    return User.objects.create(**defaults)


def _mapping(association, user, *, identity_key="email", identity_value="lanyu@example.com", snapshot=None):
    return IMNotificationUserMapping.objects.create(
        account_association=association,
        user=user,
        external_identity_key=identity_key,
        external_identity_value=identity_value,
        external_receive_key="user_id",
        external_snapshot=snapshot or {"email": identity_value, "open_id": SENDER, "user_id": "zhangsan"},
    )


def _skill():
    return LLMSkill.objects.create(name=f"skill-{uuid.uuid4().hex[:8]}", team=[1], usage_team=[1])


def _channel(channel_type, association=None, config=None, usage_team=None):
    return SkillChannel.objects.create(
        skill=_skill(),
        name=f"channel-{uuid.uuid4().hex[:8]}",
        channel_type=channel_type,
        account_association=association,
        channel_config=config or {},
        usage_team=[1] if usage_team is None else usage_team,
        enabled=True,
    )


def _save_channel(channel_type, config, association_id, *, instance=None):
    data = {
        "skill": (instance.skill_id if instance else _skill().id),
        "name": f"saved-{uuid.uuid4().hex[:8]}",
        "channel_type": channel_type,
        "channel_config": config,
        "account_association": association_id,
        "enabled": True,
    }
    serializer = SkillChannelSerializer(instance=instance, data=data, partial=bool(instance))
    return serializer


def test_serializer_accepts_wecom_association_with_the_same_identity():
    association = _association("wecom", _instance("wecom", "wecom", corp_id="ww1", agent_id="1001"))
    serializer = _save_channel(
        SkillChannelChoices.ENTERPRISE_WECHAT,
        {"corp_id": "ww1", "agent_id": "1001", "token": "t", "secret": "s", "aes_key": "k"},
        association.id,
    )
    assert serializer.is_valid(), serializer.errors
    channel = serializer.save()
    assert channel.account_association_id == association.id


def test_serializer_rejects_association_from_another_corp():
    association = _association("wecom", _instance("wecom", "wecom", corp_id="ww1", agent_id="1001"))
    serializer = _save_channel(
        SkillChannelChoices.ENTERPRISE_WECHAT,
        {"corp_id": "ww2", "agent_id": "1001"},
        association.id,
    )
    assert not serializer.is_valid()
    assert "account_association" in serializer.errors


def test_aibot_accepts_any_wecom_association():
    association = _association("wecom", _instance("wecom", "wecom", corp_id="ww1", agent_id="1001"))
    serializer = _save_channel(
        SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT,
        {"connectionMode": "websocket", "websocket": {"botId": "bot", "secret": "sec"}},
        association.id,
    )
    assert serializer.is_valid(), serializer.errors
    assert serializer.save().account_association_id == association.id


def test_platform_channel_clears_association():
    association = _association("wecom", _instance("wecom", "wecom", corp_id="ww1", agent_id="1001"))
    serializer = _save_channel(SkillChannelChoices.PLATFORM, {}, association.id)
    assert serializer.is_valid(), serializer.errors
    assert serializer.save().account_association_id is None


def test_options_follow_channel_identity(super_client):
    wecom = _association("wecom-task", _instance("wecom", "wecom", corp_id="ww1", agent_id="1001"))
    _association("other-corp", _instance("other", "wecom", corp_id="ww2", agent_id="1001"))
    feishu = _association("feishu-task", _instance("feishu", "feishu", app_id="cli_1"))
    dingtalk = _association("ding-task", _instance("ding", "dingtalk", client_id="ding-1"))
    url = reverse("skill_channel-account-association-options")

    def rows(**params):
        # DRF CustomRenderer 会再包一层 result/data。
        return super_client.get(url, params).json()["data"]["data"]

    wecom_rows = rows(channel_type="enterprise_wechat", corp_id="ww1", agent_id="1001")
    assert [item["id"] for item in wecom_rows] == [wecom.id]
    assert rows(channel_type="enterprise_wechat", corp_id="ww1") == []

    aibot_rows = rows(channel_type="enterprise_wechat_aibot")
    assert {item["id"] for item in aibot_rows} == {wecom.id, _association_id_by_name("other-corp")}

    feishu_rows = rows(channel_type="feishu", app_id="cli_1")
    assert [item["id"] for item in feishu_rows] == [feishu.id]
    assert rows(channel_type="feishu") == []

    ding_rows = rows(channel_type="dingtalk", client_id="ding-1")
    assert [item["id"] for item in ding_rows] == [dingtalk.id]
    assert rows(channel_type="wechat_official", app_id="cli_1") == []
    assert rows(channel_type="platform") == []


def _association_id_by_name(name):
    return IMAccountAssociation.objects.get(name=name).id


def test_wecom_sender_matches_userid_snapshot():
    association = _association("wecom", _instance("wecom", "wecom", corp_id="ww1", agent_id="1001"))
    user = _user()
    _mapping(
        association,
        user,
        identity_key="userid",
        identity_value="zhangsan",
        snapshot={"userid": "zhangsan", "name": "张三"},
    )
    aibot = _channel(SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT, association)
    app = _channel(
        SkillChannelChoices.ENTERPRISE_WECHAT,
        association,
        {"corp_id": "ww1", "agent_id": "1001"},
    )
    assert resolve_skill_channel_actor(aibot, "zhangsan").id == user.id
    assert resolve_skill_channel_actor(app, "zhangsan").id == user.id


def test_dingtalk_sender_matches_userid_snapshot():
    association = _association("dingtalk", _instance("ding", "dingtalk", client_id="ding-1"))
    user = _user()
    _mapping(
        association,
        user,
        identity_key="userid",
        identity_value="zhangsan",
        snapshot={"userid": "zhangsan", "name": "张三"},
    )
    channel = _channel(SkillChannelChoices.DINGTALK, association, {"client_id": "ding-1", "client_secret": "sec"})
    assert resolve_skill_channel_actor(channel, "zhangsan").id == user.id


def test_open_id_snapshot_resolves_platform_user_when_match_field_is_email():
    association = _association("feishu", _instance("feishu", "feishu", app_id="cli_1"))
    user = _user()
    _mapping(association, user)
    channel = _channel(SkillChannelChoices.FEISHU, association, {"app_id": "cli_1"})
    assert resolve_skill_channel_actor(channel, SENDER).id == user.id


def test_unusable_sender_does_not_resolve():
    association = _association("feishu", _instance("feishu", "feishu", app_id="cli_1"))
    user = _user()
    _mapping(association, user)
    channel = _channel(SkillChannelChoices.FEISHU, association, {"app_id": "cli_1"})

    association.status = "needs_resync"
    association.save(update_fields=["status"])
    with pytest.raises(Exception) as not_ready:
        resolve_skill_channel_actor(channel, SENDER)
    assert not_ready.value.reason == "not_ready"

    association.status = "ready"
    association.save(update_fields=["status"])
    user.disabled = True
    user.save(update_fields=["disabled"])
    with pytest.raises(Exception) as disabled:
        resolve_skill_channel_actor(channel, SENDER)
    assert disabled.value.reason == "disabled"

    user.disabled = False
    user.save(update_fields=["disabled"])
    other = _user(group_list=[{"id": 1, "name": "org"}])
    _mapping(association, other, identity_value="other@example.com", snapshot={"email": "other@example.com", "open_id": SENDER})
    with pytest.raises(Exception) as conflict:
        resolve_skill_channel_actor(channel, SENDER)
    assert conflict.value.reason == "conflict"


def test_conflict_record_blocks_a_single_mapping():
    association = _association("feishu", _instance("feishu", "feishu", app_id="cli_1"))
    user = _user()
    _mapping(association, user)
    IMNotificationSyncRun.objects.create(
        account_association=association,
        status=IMNotificationSyncRunStatusChoices.SUCCESS,
        payload={"conflict_user_ids": [user.id]},
    )
    channel = _channel(SkillChannelChoices.FEISHU, association, {"app_id": "cli_1"})
    with pytest.raises(Exception) as conflict:
        resolve_skill_channel_actor(channel, SENDER)
    assert conflict.value.reason == "conflict"


def test_permission_uses_usage_team_after_identify():
    association = _association("feishu", _instance("feishu", "feishu", app_id="cli_1"))
    user = _user(group_list=[{"id": 9, "name": "other"}])
    _mapping(association, user)
    channel = _channel(SkillChannelChoices.FEISHU, association, {"app_id": "cli_1"}, usage_team=[1])
    with pytest.raises(Exception) as forbidden:
        resolve_skill_channel_actor(channel, SENDER)
    assert forbidden.value.reason == "forbidden"

    guest = _user(group_list=[{"id": 1, "name": "OpsPilotGuest"}])
    _mapping(association, guest, identity_value="guest@example.com", snapshot={"open_id": "ou_guest"})
    assert resolve_skill_channel_actor(channel, "ou_guest").id == guest.id


def test_forbidden_reply_names_the_organization():
    association = _association("feishu", _instance("feishu", "feishu", app_id="cli_1"))
    user = _user(group_list=[{"id": 9, "name": "other"}])
    _mapping(association, user)
    channel = _channel(SkillChannelChoices.FEISHU, association, {"app_id": "cli_1"}, usage_team=[1])
    with patch("apps.opspilot.services.chat_service.chat_service.chat") as chat:
        text = execute_skill_channel_im_sync(channel=channel, user_message="hi", external_user_id=SENDER)
    chat.assert_not_called()
    assert text == SENDER_DENIED_TEXT["forbidden"]
    assert len(set(SENDER_DENIED_TEXT.values())) == len(SENDER_DENIED_TEXT)


def test_missing_association_keeps_the_external_identity(caplog):
    channel = _channel(SkillChannelChoices.FEISHU, None, {"app_id": "cli_1"})
    captured = {}

    def fake_chat(params):
        captured.update(params)
        return {"content": "hello"}

    with (
        patch("apps.opspilot.services.skill_channel_chat_service.inject_skill_memory_prompt"),
        patch("apps.opspilot.services.skill_channel_chat_service.maybe_schedule_skill_memory_write"),
        patch("apps.opspilot.services.python_sandbox.attachments.issue_attachment_grant", return_value="grant"),
        patch("apps.opspilot.services.chat_service.chat_service.chat", side_effect=fake_chat),
    ):
        text = execute_skill_channel_im_sync(channel=channel, user_message="hi", external_user_id=SENDER)
    assert text == "hello"
    assert captured["user_id"] is None
    assert captured["username"] == SENDER
    assert SkillConversation.objects.get().external_user_id == SENDER


def test_denied_sender_does_not_execute_or_log_the_sender(caplog):
    association = _association("feishu", _instance("feishu", "feishu", app_id="cli_1"), status="pending_sync")
    channel = _channel(SkillChannelChoices.FEISHU, association, {"app_id": "cli_1"})
    caplog.set_level(logging.INFO, logger="opspilot")
    with patch("apps.opspilot.services.chat_service.chat_service.chat") as chat:
        text = execute_skill_channel_im_sync(channel=channel, user_message="hi", external_user_id=SENDER)
    chat.assert_not_called()
    assert text == SENDER_DENIED_TEXT["not_ready"]
    assert SkillConversation.objects.count() == 0
    record = next(item for item in caplog.records if item.msg == SENDER_NOT_EXECUTABLE_LOG)
    assert record.args == (channel.id, association.id, "not_ready")
    rendered = record.getMessage()
    formatted = logging.Formatter().format(record)
    assert SENDER not in rendered
    assert SENDER not in formatted
    assert SENDER not in caplog.text


def test_matched_sender_executes_as_the_platform_user():
    association = _association("feishu", _instance("feishu", "feishu", app_id="cli_1"))
    user = _user(username="lanyu", locale="zh-Hans", timezone="Asia/Shanghai")
    _mapping(association, user)
    channel = _channel(SkillChannelChoices.FEISHU, association, {"app_id": "cli_1"})
    captured = {}

    def fake_chat(params):
        captured.update(params)
        return {"content": "done"}

    with (
        patch("apps.opspilot.services.skill_channel_chat_service.inject_skill_memory_prompt"),
        patch("apps.opspilot.services.skill_channel_chat_service.maybe_schedule_skill_memory_write"),
        patch("apps.opspilot.services.python_sandbox.attachments.issue_attachment_grant", return_value="grant"),
        patch("apps.opspilot.services.chat_service.chat_service.chat", side_effect=fake_chat),
    ):
        text = execute_skill_channel_im_sync(channel=channel, user_message="hi", external_user_id=SENDER)
    assert text == "done"
    assert captured["user_id"] == user.id
    assert captured["username"] == "lanyu"
    assert captured["locale"] == "zh-Hans"
    assert SkillConversation.objects.get().external_user_id == SENDER


def test_long_connection_closes_without_running_the_agent():
    from apps.opspilot.services.skill_channel_aibot_long_connection_agent import _run

    association = _association("wecom", _instance("wecom", "wecom"))
    channel = _channel(SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT, association)
    failed = {}
    request = SimpleNamespace(
        channel=channel,
        external_user_id="zhangsan",
        user_message="hi",
        session_id="room",
        cancelled=False,
        fail=lambda message=None: failed.setdefault("message", message),
        publish=lambda text: None,
        finish=lambda: None,
    )
    with patch("apps.opspilot.utils.agui_chat._generate_agui_stream", side_effect=AssertionError("agent should not run")):
        _run(request)
    assert failed["message"] == SENDER_DENIED_TEXT["not_associated"]


def test_long_connection_without_association_still_runs(monkeypatch):
    from apps.opspilot.services.skill_channel_aibot_long_connection_agent import _run

    channel = _channel(SkillChannelChoices.ENTERPRISE_WECHAT_AIBOT, None)
    captured = {}

    async def fake_stream(params, *args, **kwargs):
        captured["username"] = params.get("username")
        if False:
            yield ""

    monkeypatch.setattr("apps.opspilot.utils.agui_chat._generate_agui_stream", fake_stream)
    monkeypatch.setattr(
        "apps.opspilot.services.skill_channel_chat_service.get_or_create_conversation",
        lambda *args, **kwargs: SimpleNamespace(session_id="session-1"),
    )
    monkeypatch.setattr(
        "apps.opspilot.services.skill_channel_chat_service.build_skill_chat_params",
        lambda *args, **kwargs: {"username": args[2].username, "user_id": args[2].id},
    )
    monkeypatch.setattr(
        "apps.opspilot.services.skill_channel_chat_service._history_from_conversation",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr("apps.opspilot.services.skill_memory_service.inject_skill_memory_prompt", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "apps.opspilot.services.skill_channel_aibot_long_connection_agent._files_for_execution",
        lambda execution_id, channel_id: [],
    )
    request = SimpleNamespace(
        channel=channel,
        external_user_id="zhangsan",
        session_id="room",
        user_message="hi",
        cancelled=False,
        publish=lambda text: None,
        finish=lambda: None,
        fail=lambda message=None: None,
    )
    _run(request)
    assert captured["username"] == "zhangsan"
