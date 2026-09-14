"""智能体渠道对话记忆：用户自选个人记忆体、读取注入、水位线写入与删除保留。"""

import json
import logging
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.models import User
from apps.opspilot.enum import SkillChannelChoices
from apps.opspilot.models import LLMSkill, MemorySpace, SkillChannel, SkillConversation, SkillConversationMessage
from apps.opspilot.services.skill_channel_chat_service import delete_skill_session, execute_skill_channel_im_sync, list_skill_conversations_for_user
from apps.opspilot.services.skill_memory_service import (
    _SKILL_MEMORY_EMPTY_LOG,
    _SKILL_MEMORY_INJECTED_LOG,
    SKILL_CONVERSATION_SUMMARY_PROMPT,
    SKILL_MEMORY_WRITE_ROUNDS_DEFAULT,
    SkillMemoryConfigError,
    append_skill_memory_block,
    format_conversation_transcript,
    inject_skill_memory_prompt,
    iter_idle_skill_conversation_ids,
    maybe_schedule_skill_memory_write,
    validate_skill_memory_binding,
)
from apps.opspilot.tasks.memory import (
    _SKILL_MEMORY_WRITE_DEFERRED_LOG,
    MemoryWriteLlmUnavailable,
    _summarize_skill_conversation_content,
    write_skill_conversation_memory,
)
from apps.opspilot.viewsets.llm_view import LLMViewSet
from apps.system_mgmt.models import User as SystemUser

pytestmark = pytest.mark.django_db


def _superuser(username="skill_mem_su"):
    user = User.objects.create_user(
        username=username,
        password="x",
        domain="domain.com",
        locale="en",
        group_list=[{"id": 1, "name": "T1"}, {"id": 2, "name": "T2"}],
        roles=["admin"],
    )
    user.is_superuser = True
    user.save()
    return user


def _personal_space(**kwargs):
    defaults = {"name": "个人记忆", "scope": MemorySpace.SCOPE_PERSONAL, "team": [1]}
    defaults.update(kwargs)
    return MemorySpace.objects.create(**defaults)


def _skill(**kwargs):
    defaults = {"name": "mem-skill", "team": [1], "usage_team": [1], "skill_prompt": "你是助手"}
    defaults.update(kwargs)
    return LLMSkill.objects.create(**defaults)


def _channel(skill, **kwargs):
    defaults = {
        "skill": skill,
        "channel_type": SkillChannelChoices.WEB_CHAT,
        "enabled": True,
        "usage_team": [1],
        "name": "web",
    }
    defaults.update(kwargs)
    return SkillChannel.objects.create(**defaults)


def _conversation(skill, channel, external_user_id="alice@domain.com"):
    return SkillConversation.objects.create(
        session_id="sid-mem-1",
        skill=skill,
        channel=channel,
        external_user_id=external_user_id,
    )


def _turns(conversation, n):
    for i in range(n):
        SkillConversationMessage.objects.create(conversation=conversation, role="user", content=f"u{i}")
        SkillConversationMessage.objects.create(conversation=conversation, role="assistant", content=f"a{i}")


def _memory_skill(**kwargs):
    space = kwargs.pop("memory_space", None) or _personal_space()
    kwargs.setdefault("memory_write_rounds", SKILL_MEMORY_WRITE_ROUNDS_DEFAULT)
    return _skill(memory_space=space, **kwargs), space


class TestSkillMemoryConfig:
    def test_new_skill_does_not_bind_memory(self):
        skill = _skill()
        assert skill.memory_space_id is None

    def test_update_accepts_personal_space_and_rounds(self):
        skill = _skill()
        other = _personal_space()
        factory = APIRequestFactory()
        user = _superuser("su-upd")
        request = factory.put(
            "/",
            {"name": skill.name, "team": [1], "memory_space": other.id, "memory_write_rounds": 3},
            format="json",
        )
        force_authenticate(request, user=user)
        request.COOKIES["current_team"] = "1"
        resp = LLMViewSet.as_view({"put": "update"})(request, pk=skill.id)
        assert resp.status_code == 200
        assert json.loads(resp.content.decode("utf-8"))["result"] is True
        skill.refresh_from_db()
        assert skill.memory_space_id == other.id
        assert skill.memory_write_rounds == 3

    def test_update_rejects_team_space(self):
        skill = _skill()
        team_space = MemorySpace.objects.create(name="团队知识", scope=MemorySpace.SCOPE_TEAM, team=[1])
        factory = APIRequestFactory()
        user = _superuser("su-team")
        request = factory.put(
            "/",
            {"name": skill.name, "team": [1], "memory_space": team_space.id},
            format="json",
        )
        force_authenticate(request, user=user)
        request.COOKIES["current_team"] = "1"
        resp = LLMViewSet.as_view({"put": "update"})(request, pk=skill.id)
        assert json.loads(resp.content.decode("utf-8"))["result"] is False
        skill.refresh_from_db()
        assert skill.memory_space_id is None

    def test_update_can_clear_memory_space(self):
        skill, _ = _memory_skill()
        factory = APIRequestFactory()
        user = _superuser("su-clear")
        request = factory.put(
            "/",
            {"name": skill.name, "team": [1], "memory_space": None},
            format="json",
        )
        force_authenticate(request, user=user)
        request.COOKIES["current_team"] = "1"
        resp = LLMViewSet.as_view({"put": "update"})(request, pk=skill.id)
        assert json.loads(resp.content.decode("utf-8"))["result"] is True
        skill.refresh_from_db()
        assert skill.memory_space_id is None

    def test_binding_rejects_team_and_foreign_org(self):
        team_space = MemorySpace.objects.create(name="团队知识", scope=MemorySpace.SCOPE_TEAM, team=[1])
        with pytest.raises(SkillMemoryConfigError):
            validate_skill_memory_binding(team_space.id)
        space = _personal_space(team=[99])
        user = SimpleNamespace(is_superuser=False, group_list=[{"id": 1}])
        with pytest.raises(SkillMemoryConfigError):
            validate_skill_memory_binding(space.id, user)
        su = SimpleNamespace(is_superuser=True, group_list=[])
        assert validate_skill_memory_binding(space.id, su).id == space.id
        assert validate_skill_memory_binding(None) is None


class TestSkillMemoryReadInject:
    def test_injects_and_moves_after_wiki(self):
        skill, _ = _memory_skill()
        engine = MagicMock()
        engine.read.return_value = SimpleNamespace(context="喜欢咖啡")
        with patch("apps.opspilot.memory.engines.registry.MemoryEngineRegistry.get_engine", return_value=engine):
            params = {"skill_prompt": "你是助手"}
            inject_skill_memory_prompt(params, skill, "alice@domain.com", "早上好")
        prompt = params["skill_prompt"]
        assert prompt.startswith("你是助手")
        assert "## 用户记忆" in prompt
        assert "喜欢咖啡" in prompt
        assert "跨会话持续有效" in prompt
        assert "不要另起一套通用清单" in prompt
        assert params["skill_memory_block"].startswith("## 用户记忆")
        wiki = f"{prompt}\n\n【相关知识库信息】wiki-hit"
        placed = append_skill_memory_block(wiki, params["skill_memory_block"])
        assert placed.index("【相关知识库信息】") < placed.index("## 用户记忆")
        engine.read.assert_called_once()
        assert engine.read.call_args.kwargs["entity"].user_id == "alice@domain.com"

    def test_injects_for_system_user_uuid(self):
        user_id = str(uuid4())
        skill, _ = _memory_skill()
        engine = MagicMock()
        engine.read.return_value = SimpleNamespace(context="Oracle P0：表空间 > 90%")
        with patch("apps.opspilot.memory.engines.registry.MemoryEngineRegistry.get_engine", return_value=engine):
            params = {"skill_prompt": "你是助手"}
            inject_skill_memory_prompt(params, skill, user_id, "Oracle常规巡检")
        assert "Oracle P0：表空间 > 90%" in params["skill_prompt"]
        assert engine.read.call_args.kwargs["entity"].user_id == user_id

    def test_inject_logs_counts_not_memory_body(self, caplog):
        skill, space = _memory_skill()
        engine = MagicMock()
        engine.read.return_value = SimpleNamespace(context="喜欢咖啡")
        caplog.set_level(logging.DEBUG, logger="opspilot")
        with patch("apps.opspilot.memory.engines.registry.MemoryEngineRegistry.get_engine", return_value=engine):
            inject_skill_memory_prompt({"skill_prompt": "你是助手"}, skill, "alice@domain.com", "早上好")
        records = [item for item in caplog.records if item.msg == _SKILL_MEMORY_INJECTED_LOG]
        assert len(records) == 1
        assert records[0].args == (skill.id, space.id, len("喜欢咖啡"))
        assert records[0].getMessage() == _SKILL_MEMORY_INJECTED_LOG % (skill.id, space.id, len("喜欢咖啡"))
        assert "喜欢咖啡" not in records[0].getMessage()

    def test_empty_memory_logs_without_query(self, caplog):
        skill, space = _memory_skill()
        engine = MagicMock()
        engine.read.return_value = SimpleNamespace(context="  ")
        caplog.set_level(logging.DEBUG, logger="opspilot")
        question = "Oracle常规巡检Top"
        with patch("apps.opspilot.memory.engines.registry.MemoryEngineRegistry.get_engine", return_value=engine):
            params = inject_skill_memory_prompt({"skill_prompt": "你是助手"}, skill, "alice@domain.com", question)
        assert "用户记忆" not in (params.get("skill_prompt") or "")
        records = [item for item in caplog.records if item.msg == _SKILL_MEMORY_EMPTY_LOG]
        assert records[0].args == (skill.id, space.id)
        assert question not in caplog.text

    def test_skips_when_memory_not_configured(self):
        skill = _skill()
        engine = MagicMock()
        with patch("apps.opspilot.memory.engines.registry.MemoryEngineRegistry.get_engine", return_value=engine):
            params = inject_skill_memory_prompt({"skill_prompt": "你是助手"}, skill, "alice@domain.com", "早上好")
        assert "用户记忆" not in (params.get("skill_prompt") or "")
        engine.read.assert_not_called()

    def test_im_chat_does_not_persist_memory_block(self):
        skill, _ = _memory_skill()
        channel = _channel(skill)
        engine = MagicMock()
        engine.read.return_value = SimpleNamespace(context="喜欢茶")
        with patch("apps.opspilot.memory.engines.registry.MemoryEngineRegistry.get_engine", return_value=engine), patch(
            "apps.opspilot.services.chat_service.chat_service.chat", return_value={"content": "好的"}
        ) as chat:
            execute_skill_channel_im_sync(channel=channel, user_message="你好", external_user_id="alice@domain.com")
        prompt = chat.call_args.args[0]["skill_prompt"]
        assert "## 用户记忆" in prompt
        assert chat.call_args.args[0]["skill_memory_block"].startswith("## 用户记忆")
        history = chat.call_args.args[0]["chat_history"]
        assert all("用户记忆" not in str(item) for item in history)
        stored = SkillConversationMessage.objects.filter(role="user").first()
        assert stored is not None
        assert "用户记忆" not in stored.content
        assert stored.content == "你好"


class TestSkillMemoryWriteWatermark:
    def test_schedules_after_skill_threshold(self):
        skill, _ = _memory_skill(memory_write_rounds=3)
        channel = _channel(skill)
        conv = _conversation(skill, channel)
        _turns(conv, 3 - 1)
        with patch("apps.opspilot.tasks.memory.write_skill_conversation_memory.delay") as delay:
            assert maybe_schedule_skill_memory_write(conv) is False
            delay.assert_not_called()
        _turns(conv, 1)
        with patch("apps.opspilot.tasks.memory.write_skill_conversation_memory.delay") as delay:
            assert maybe_schedule_skill_memory_write(conv) is True
            delay.assert_called_once_with(conv.id)

    def test_does_not_schedule_when_unbound(self):
        skill = _skill()
        channel = _channel(skill)
        conv = _conversation(skill, channel)
        _turns(conv, 10)
        with patch("apps.opspilot.tasks.memory.write_skill_conversation_memory.delay") as delay:
            assert maybe_schedule_skill_memory_write(conv) is False
            delay.assert_not_called()

    def test_write_skips_unbound_skill(self):
        skill = _skill()
        channel = _channel(skill)
        conv = _conversation(skill, channel)
        _turns(conv, 1)
        with patch("apps.opspilot.tasks.memory.close_old_connections"), patch("apps.opspilot.tasks.memory._commit_memory_write_with_retry") as commit:
            write_skill_conversation_memory.run(conv.id)
        commit.assert_not_called()
        conv.refresh_from_db()
        assert conv.memory_written_message_id == 0

    def test_write_advances_watermark(self):
        skill, space = _memory_skill()
        channel = _channel(skill)
        conv = _conversation(skill, channel)
        _turns(conv, 2)
        last_id = conv.messages.order_by("id").last().id
        with patch("apps.opspilot.tasks.memory.close_old_connections"), patch(
            "apps.opspilot.tasks.memory._summarize_skill_conversation_content", return_value="喜欢咖啡"
        ), patch("apps.opspilot.tasks.memory._commit_memory_write_with_retry", return_value=(None, "applied")) as commit:
            write_skill_conversation_memory.run(conv.id)
        conv.refresh_from_db()
        assert conv.memory_written_message_id == last_id
        assert commit.call_args.kwargs["title"] == "对话记忆"
        assert commit.call_args.kwargs["skip_write_rule"] is False
        assert commit.call_args.kwargs["owner_username"] == "alice"
        assert commit.call_args.kwargs["owner_domain"] == "domain.com"
        assert commit.call_args.kwargs["owner_user_id"] is None
        assert commit.call_args.kwargs["memory_space_id"] == space.id

    def test_write_uses_system_user_uuid(self):
        user_id = str(uuid4())
        SystemUser.objects.create(
            username="alice",
            domain="domain.com",
            display_name="alice",
            email="alice@domain.com",
            password="x",
            user_id=user_id,
        )
        skill, _ = _memory_skill()
        channel = _channel(skill)
        conv = _conversation(skill, channel, external_user_id=user_id)
        _turns(conv, 1)
        with patch("apps.opspilot.tasks.memory.close_old_connections"), patch(
            "apps.opspilot.tasks.memory._summarize_skill_conversation_content", return_value="喜欢茶"
        ), patch("apps.opspilot.tasks.memory._commit_memory_write_with_retry", return_value=(None, "applied")) as commit:
            write_skill_conversation_memory.run(conv.id)
        assert commit.call_args.kwargs["owner_user_id"] == user_id
        assert commit.call_args.kwargs["owner_username"] == "alice"
        assert commit.call_args.kwargs["owner_domain"] == "domain.com"

    def test_empty_summary_still_advances_watermark(self):
        skill, _ = _memory_skill()
        channel = _channel(skill)
        conv = _conversation(skill, channel)
        _turns(conv, 1)
        last_id = conv.messages.order_by("id").last().id
        with patch("apps.opspilot.tasks.memory.close_old_connections"), patch(
            "apps.opspilot.tasks.memory._summarize_skill_conversation_content", return_value=""
        ), patch("apps.opspilot.tasks.memory._commit_memory_write_with_retry") as commit:
            write_skill_conversation_memory.run(conv.id)
        conv.refresh_from_db()
        assert conv.memory_written_message_id == last_id
        commit.assert_not_called()

    def test_llm_failure_keeps_watermark(self, caplog):
        skill, _ = _memory_skill()
        channel = _channel(skill)
        conv = _conversation(skill, channel)
        _turns(conv, 1)
        caplog.set_level(logging.WARNING, logger="opspilot")
        with patch("apps.opspilot.tasks.memory.close_old_connections"), patch(
            "apps.opspilot.tasks.memory._summarize_skill_conversation_content",
            side_effect=MemoryWriteLlmUnavailable("down", failed_stage="summarize"),
        ):
            with pytest.raises(MemoryWriteLlmUnavailable):
                write_skill_conversation_memory.run(conv.id)
        conv.refresh_from_db()
        assert conv.memory_written_message_id == 0
        records = [r for r in caplog.records if r.msg == _SKILL_MEMORY_WRITE_DEFERRED_LOG]
        assert len(records) == 1
        assert records[0].levelno == logging.WARNING
        assert records[0].args[2] == "summarize"
        assert records[0].exc_info is None

    def test_summary_prompt_drops_greetings_and_ignores_space_write_rule(self):
        space = _personal_space()
        space.write_rule = "把所有寒暄都留下来"
        space.save(update_fields=["write_rule"])
        client = MagicMock()
        client.invoke.return_value = SimpleNamespace(content="EMPTY")
        with patch("apps.opspilot.tasks.memory._build_memory_write_client", return_value=client):
            summarized = _summarize_skill_conversation_content(space, "用户：你好\n\n助手：您好", model_id=1)
        assert summarized == ""
        human = client.invoke.call_args.args[0][1].content
        assert "寒暄问好" in human
        assert "环境与资产" in human
        assert "检查约定" in human
        assert "禁止只写" in human or "不能只写" in human
        assert "EMPTY" in SKILL_CONVERSATION_SUMMARY_PROMPT
        assert "把所有寒暄都留下来" not in human

    def test_transcript_uses_visible_assistant_text(self):
        agui = json.dumps(
            [
                {"type": "TOOL_CALL_START", "toolCallName": "run_sql"},
                {"type": "TEXT_MESSAGE_CONTENT", "delta": "Oracle 表空间使用率 82%"},
            ],
            ensure_ascii=False,
        )
        text = format_conversation_transcript(
            [
                {"role": "user", "content": "查一下表空间"},
                {"role": "assistant", "content": agui},
            ]
        )
        assert "Oracle 表空间使用率 82%" in text
        assert "TOOL_CALL_START" not in text
        assert "run_sql" not in text

    def test_transcript_keeps_head_and_recent_when_over_budget(self, monkeypatch):
        import apps.opspilot.services.skill_memory_service as skill_memory_service

        monkeypatch.setattr(skill_memory_service, "SKILL_MEMORY_TRANSCRIPT_MAX_CHARS", 160)
        monkeypatch.setattr(skill_memory_service, "SKILL_MEMORY_MESSAGE_MAX_CHARS", 200)
        text = format_conversation_transcript(
            [
                {"role": "user", "content": "HEAD_MARKER incident"},
                {"role": "assistant", "content": "head-answer"},
                {"role": "user", "content": "MID_MARKER " + ("m" * 80)},
                {"role": "assistant", "content": "mid-answer " + ("z" * 80)},
                {"role": "user", "content": "LATE_MARKER 表空间告警"},
                {"role": "assistant", "content": "LATE_FINDING 82%"},
            ]
        )
        assert "HEAD_MARKER" in text
        assert "LATE_FINDING" in text
        assert "MID_MARKER" not in text

    def test_idle_flush_skips_recent_only(self):
        skill, _ = _memory_skill()
        channel = _channel(skill)
        idle = _conversation(skill, channel)
        _turns(idle, 1)
        SkillConversationMessage.objects.filter(conversation=idle).update(created_at=timezone.now() - timedelta(hours=2))

        recent = SkillConversation.objects.create(
            session_id="sid-recent",
            skill=skill,
            channel=channel,
            external_user_id="bob@domain.com",
        )
        _turns(recent, 1)

        other, _ = _memory_skill(name="other-skill")
        other_ch = _channel(other, name="web2")
        other_conv = SkillConversation.objects.create(
            session_id="sid-other",
            skill=other,
            channel=other_ch,
            external_user_id="carol@domain.com",
        )
        _turns(other_conv, 1)
        SkillConversationMessage.objects.filter(conversation=other_conv).update(created_at=timezone.now() - timedelta(hours=2))

        unbound = _skill(name="unbound-skill")
        unbound_ch = _channel(unbound, name="web3")
        unbound_conv = SkillConversation.objects.create(
            session_id="sid-unbound",
            skill=unbound,
            channel=unbound_ch,
            external_user_id="dave@domain.com",
        )
        _turns(unbound_conv, 1)
        SkillConversationMessage.objects.filter(conversation=unbound_conv).update(created_at=timezone.now() - timedelta(hours=2))

        ids = iter_idle_skill_conversation_ids(idle_minutes=30)
        assert idle.id in ids
        assert recent.id not in ids
        assert other_conv.id in ids
        assert unbound_conv.id not in ids


class TestSkillMemoryDeleteAndList:
    def test_pending_rounds_and_keep_memory_snapshot(self):
        skill, space = _memory_skill()
        channel = _channel(skill)
        conv = _conversation(skill, channel)
        _turns(conv, 2)
        rows = list_skill_conversations_for_user(skill_id=skill.id, channel_id=channel.id, external_user_id="alice@domain.com")
        assert rows[0]["pending_memory_rounds"] == 2
        with patch("apps.opspilot.tasks.memory.write_skill_conversation_memory.delay") as delay:
            delete_skill_session(session_id=conv.session_id, external_user_id="alice@domain.com", keep_memory=True)
        delay.assert_called_once()
        assert delay.call_args.args[1] is True
        assert isinstance(delay.call_args.args[2], list)
        assert delay.call_args.args[2]
        assert delay.call_args.args[3] == space.id
        assert not SkillConversation.objects.filter(id=conv.id).exists()

    def test_delete_without_keep_memory_does_not_write(self):
        skill = _skill()
        channel = _channel(skill)
        conv = _conversation(skill, channel)
        _turns(conv, 1)
        with patch("apps.opspilot.tasks.memory.write_skill_conversation_memory.delay") as delay:
            delete_skill_session(session_id=conv.session_id, external_user_id="alice@domain.com", keep_memory=False)
        delay.assert_not_called()
        assert not SkillConversation.objects.filter(id=conv.id).exists()

    def test_unbound_skill_hides_pending_and_skips_keep_memory(self):
        skill = _skill()
        channel = _channel(skill)
        conv = _conversation(skill, channel)
        _turns(conv, 2)
        rows = list_skill_conversations_for_user(skill_id=skill.id, channel_id=channel.id, external_user_id="alice@domain.com")
        assert rows[0]["pending_memory_rounds"] == 0
        with patch("apps.opspilot.tasks.memory.write_skill_conversation_memory.delay") as delay:
            delete_skill_session(session_id=conv.session_id, external_user_id="alice@domain.com", keep_memory=True)
        delay.assert_not_called()
