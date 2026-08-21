"""skill_channel 对话 page_context：当轮注入、不落历史、超限防御。"""

from unittest.mock import patch

import pytest
from django.http import StreamingHttpResponse
from rest_framework.test import APIRequestFactory

from apps.base.models import User
from apps.opspilot.enum import SkillChannelChoices
from apps.opspilot.models import LLMSkill, SkillChannel, SkillConversation, SkillConversationMessage
from apps.opspilot.services import skill_channel_chat_service as chat_svc

pytestmark = pytest.mark.django_db


def _superuser(username="page_ctx_su"):
    user = User.objects.create_user(
        username=username,
        password="x",
        domain="domain.com",
        locale="en",
        group_list=[{"id": 1, "name": "T1"}],
        roles=["admin"],
    )
    user.is_superuser = True
    user.save()
    return user


def _skill():
    return LLMSkill.objects.create(name="page-ctx-skill", team=[1], usage_team=[1])


def _channel(skill):
    return SkillChannel.objects.create(
        skill=skill,
        channel_type=SkillChannelChoices.PLATFORM,
        enabled=True,
        usage_team=[1],
        name="platform",
    )


def _tiny_png_data_url():
    return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


def _stream_request(user, message="hi"):
    factory = APIRequestFactory()
    request = factory.post("/", {"message": message}, format="json")
    request.user = user
    return request


def _patched_stream():
    def gen():
        yield b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
        yield b"data: [DONE]\n\n"

    return patch(
        "apps.opspilot.services.skill_channel_chat_service.stream_agui_chat",
        return_value=StreamingHttpResponse(gen(), content_type="text/event-stream"),
    )


class TestInjectPageContext:
    def test_wraps_text_and_images(self):
        result = chat_svc.inject_page_context(
            "现在几点了",
            {
                "url": "/monitor/view/dashboard/host",
                "title": "host",
                "sections": [{"id": "meta", "label": "对象", "content": "主机 A", "priority": 10}],
                "images": [{"caption": "CPU", "dataUrl": _tiny_png_data_url()}],
            },
        )
        assert isinstance(result, list)
        assert result[0]["type"] == "image_url"
        assert result[0]["image_url"].startswith("data:image/png")
        text = result[-1]["message"]
        assert "现在几点了" in text
        assert "<current_page>" in text
        assert "主机 A" in text
        assert "仅当问题与页面相关时参考" in text
        assert "CPU" in text

    def test_empty_context_keeps_original(self):
        assert chat_svc.inject_page_context("hi", None) == "hi"
        assert chat_svc.inject_page_context("hi", {}) == "hi"

    def test_unknown_mode_skips(self):
        assert chat_svc.inject_page_context("hi", {"title": "x"}, mode="tool") == "hi"

    def test_drops_low_priority_when_over_budget(self):
        snapshot = {
            "sections": [
                {"id": "low", "label": "低", "content": "L" * 5000, "priority": 1},
                {"id": "high", "label": "高", "content": "H" * 5000, "priority": 9},
            ]
        }
        result = chat_svc.inject_page_context("q", snapshot)
        assert "H" * 20 in result
        assert "## 低" not in result
        assert len(result) <= 8000 + 400

    def test_drops_oversized_and_extra_images(self):
        huge = "data:image/png;base64," + ("A" * (chat_svc.PAGE_CONTEXT_MAX_IMAGE_CHARS + 10))
        images = [{"caption": f"c{i}", "dataUrl": _tiny_png_data_url()} for i in range(8)]
        images.append({"caption": "huge", "dataUrl": huge})
        result = chat_svc.inject_page_context("q", {"images": images})
        image_items = [item for item in result if item.get("type") == "image_url"]
        assert len(image_items) == 6
        assert all(len(item["image_url"]) <= chat_svc.PAGE_CONTEXT_MAX_IMAGE_CHARS for item in image_items)


class TestStreamPageContext:
    def test_injects_into_llm_params_but_persists_plain_text(self):
        skill = _skill()
        ch = _channel(skill)
        user = _superuser()
        page_context = {
            "title": "host dashboard",
            "sections": [{"id": "obj", "label": "实例", "content": "host-1", "priority": 5}],
            "images": [{"caption": "cpu", "dataUrl": _tiny_png_data_url()}],
        }
        with _patched_stream() as mock_stream:
            with patch(
                "apps.opspilot.services.skill_channel_chat_service.capture_caller_identity",
                return_value={"username": "page_ctx_su"},
            ):
                chat_svc.stream_skill_channel_chat(
                    channel=ch,
                    user_message="这个尖峰是什么",
                    request=_stream_request(user),
                    external_user_id="u@domain.com",
                    session_id="sess-pc-1",
                    page_context=page_context,
                )
        params = mock_stream.call_args.args[0]
        injected = params["user_message"]
        assert isinstance(injected, list)
        assert any(item.get("type") == "image_url" for item in injected)
        assert "host-1" in injected[-1]["message"]
        user_msgs = list(SkillConversationMessage.objects.filter(role="user"))
        assert len(user_msgs) == 1
        assert user_msgs[0].content == "这个尖峰是什么"
        assert "<current_page>" not in user_msgs[0].content
        assert "data:image" not in user_msgs[0].content

    def test_missing_page_context_matches_baseline(self):
        skill = _skill()
        ch = _channel(skill)
        user = _superuser("page_ctx_su2")
        with _patched_stream() as mock_stream:
            with patch(
                "apps.opspilot.services.skill_channel_chat_service.capture_caller_identity",
                return_value={"username": "page_ctx_su2"},
            ):
                chat_svc.stream_skill_channel_chat(
                    channel=ch,
                    user_message="hi",
                    request=_stream_request(user),
                    external_user_id="u2@domain.com",
                    session_id="sess-pc-empty",
                )
        params = mock_stream.call_args.args[0]
        assert params["user_message"] == "hi"
        assert SkillConversationMessage.objects.filter(role="user", content="hi").exists()

    def test_second_turn_keeps_only_latest_snapshot(self):
        skill = _skill()
        ch = _channel(skill)
        user = _superuser("page_ctx_su3")
        request = _stream_request(user)
        with _patched_stream() as mock_stream:
            with patch(
                "apps.opspilot.services.skill_channel_chat_service.capture_caller_identity",
                return_value={"username": "page_ctx_su3"},
            ):
                chat_svc.stream_skill_channel_chat(
                    channel=ch,
                    user_message="第一问",
                    request=request,
                    external_user_id="u3@domain.com",
                    session_id="sess-pc-2",
                    page_context={"sections": [{"id": "a", "label": "A", "content": "SNAPSHOT-A", "priority": 1}]},
                )
                conv = SkillConversation.objects.get(session_id="sess-pc-2")
                SkillConversationMessage.objects.create(
                    conversation=conv,
                    role=SkillConversationMessage.ROLE_ASSISTANT,
                    content="答一",
                )
                chat_svc.stream_skill_channel_chat(
                    channel=ch,
                    user_message="第二问",
                    request=request,
                    external_user_id="u3@domain.com",
                    session_id="sess-pc-2",
                    page_context={"sections": [{"id": "b", "label": "B", "content": "SNAPSHOT-B", "priority": 1}]},
                )
        second_params = mock_stream.call_args.args[0]
        assert "SNAPSHOT-B" in second_params["user_message"]
        assert "SNAPSHOT-A" not in second_params["user_message"]
        history_blob = str(second_params["chat_history"])
        assert "SNAPSHOT-A" not in history_blob
        assert "SNAPSHOT-B" not in history_blob
        stored = list(SkillConversationMessage.objects.filter(conversation__session_id="sess-pc-2", role="user").values_list("content", flat=True))
        assert stored == ["第一问", "第二问"]
