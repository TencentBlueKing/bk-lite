import json
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.urls import resolve
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.opspilot.models import SkillConversationMessage as Message
from apps.opspilot.tests.test_skill_admin_conversation_history import _channel, _conv, _normal, _skill, _superuser

pytestmark = pytest.mark.django_db


def _body(response):
    return json.loads(response.render().content)


def call(user, action, method="get", team="1", **data):
    url = f"/api/v1/opspilot/model_provider_mgmt/skill_channel/{action}/"
    factory = APIRequestFactory()
    request = factory.get(url, data) if method == "get" else factory.post(url, data, format="json")
    request.COOKIES["current_team"] = team
    force_authenticate(request, user=user)
    return resolve(url).func(request)


@pytest.fixture
def history():
    skill = _skill()
    conv = _conv(skill, _channel(skill, channel_type="platform"), session_id="session-A", external_user_id="alice")
    now = timezone.now()

    def add(role, content, ago):
        msg = Message.objects.create(conversation=conv, role=role, content=content)
        Message.objects.filter(pk=msg.pk).update(created_at=now - timedelta(hours=ago))
        return msg.id

    add("user", "之前的问题", 5)
    add("assistant", "之前的回答", 4)
    question = add("user", "连接失败 token=hidden-secret", 3)
    add("assistant", json.dumps([{"type": "TEXT_MESSAGE_CONTENT", "delta": "重试连接"}, {"type": "TOOL_CALL_RESULT", "content": "tool-secret"}]), 1)
    add("user", "新的问题", 0)
    return skill, conv, question, now


def test_time_window_freezes_questions_and_replies_and_exports_pdf(history, django_capture_on_commit_callbacks):
    from apps.opspilot.tasks.history_analysis import run_history_analysis

    skill, conv, question, now = history
    user = _superuser()
    scope = dict(scope="range", start=(now - timedelta(hours=3, minutes=1)).isoformat(), end=(now - timedelta(hours=2)).isoformat())
    args = dict(skill_id=skill.id, **scope)
    preview = _body(call(user, "analysis_preview", "post", **args))["data"]
    assert (preview["conversation_count"], preview["question_count"]) == (1, 1)
    args.update(name="连接报告", objective="quality", request_id=str(uuid.uuid4()))
    with patch.object(run_history_analysis, "delay") as queued, django_capture_on_commit_callbacks(execute=True):
        task = _body(call(user, "analyses", "post", **args))["data"]
        duplicate = _body(call(user, "analyses", "post", **args))["data"]
        assert duplicate["id"] == task["id"]
    queued.assert_called_once()
    payloads = []

    def analyze(task, turns):
        payloads.extend(turns)
        return [{"finding": "连接异常", "suggestion": "完善重试提示", "evidence": [question]}]

    with patch("apps.opspilot.tasks.history_analysis.analyze_turns", side_effect=analyze):
        run_history_analysis(*queued.call_args.args)
        run_history_analysis(*queued.call_args.args)
    payload = json.dumps(payloads, ensure_ascii=False)
    assert "重试连接" in payload and "之前的问题" in payload
    assert all(text not in payload for text in ("hidden-secret", "tool-secret", "新的问题"))
    report = _body(call(user, "analysis_report", skill_id=skill.id, task_id=task["id"]))["data"]
    assert report["status"] == "completed"
    assert report["findings"][0]["evidence"] == [{"session_id": conv.session_id, "message_id": question}]
    pdf = call(user, "analysis_report", skill_id=skill.id, task_id=task["id"], download="pdf")
    assert pdf["Content-Type"] == "application/pdf" and pdf.content.startswith(b"%PDF-")
    result = _body(call(user, "analyses", skill_id=skill.id))["data"]
    assert result["count"] == 1 and result["items"][0]["id"] == task["id"]
    assert _body(call(user, "analyses", skill_id=skill.id, team="2"))["data"] == {"items": [], "count": 0}
    assert call(user, "analysis_report", skill_id=skill.id, task_id=task["id"], download="pdf", team="2").status_code == 404


def test_selected_sessions_reject_foreign_or_missing_and_recheck_management(history):
    skill, conv, _, _ = history
    other = _skill(name="other")
    foreign = _conv(other, None, session_id="foreign", external_user_id="alice")
    admin = _superuser()
    args = dict(skill_id=skill.id, scope="sessions", session_ids=[conv.session_id])
    assert _body(call(admin, "analysis_preview", "post", **args))["data"]["question_count"] == 3
    for invalid in ([], [foreign.session_id], [conv.session_id, "deleted"]):
        assert call(admin, "analysis_preview", "post", **(args | {"session_ids": invalid})).status_code == 400
    user = _normal()
    for action, method in (
        ("analysis_preview", "post"),
        ("analysis_channels", "post"),
        ("analyses", "post"),
        ("analyses", "get"),
        ("analysis_report", "get"),
        ("analysis_retry", "post"),
    ):
        assert call(user, action, method, team="2", **args).status_code == 403


def test_retry_same_snapshot_and_validate_model_evidence(history, django_capture_on_commit_callbacks):
    from types import SimpleNamespace

    import fitz

    from apps.opspilot.models import LLMModel
    from apps.opspilot.tasks.history_analysis import run_history_analysis

    skill, conv, question, _ = history
    skill.llm_model = LLMModel.objects.create(name="test-model")
    skill.save()
    second = _conv(skill, None, session_id="session-B", external_user_id="bob")
    b = Message.objects.create(conversation=second, role="user", content="第二个对话")
    admin = _superuser()
    config = dict(
        skill_id=skill.id,
        scope="sessions",
        session_ids=[conv.session_id, second.session_id],
        name="诊断报告",
        objective="needs",
        request_id=str(uuid.uuid4()),
    )
    with patch.object(run_history_analysis, "delay") as queue, django_capture_on_commit_callbacks(execute=True):
        initial = _body(call(admin, "analyses", "post", **config))["data"]
    params = dict(skill_id=skill.id, task_id=initial["id"])
    late = Message.objects.create(conversation=second, role="user", content="提交后的新消息")
    assert call(admin, "analysis_report", **params, download="pdf").status_code == 409
    assert call(admin, "analysis_retry", "post", **params).status_code == 409
    finding = {"finding": "需要改进", "suggestion": "补充排查步骤", "evidence": [late.pk]}
    with patch("apps.opspilot.services.history_analysis.LLMClientFactory.create_client") as build:
        client = build.return_value
        client.invoke.return_value = SimpleNamespace(content=json.dumps([finding]))
        run_history_analysis(*queue.call_args.args)
        messages = client.invoke.call_args.args[0]
        assert "English" in messages[0].content and "第二个对话" in messages[1].content
        assert late.content not in messages[1].content
        failed = _body(call(admin, "analyses", skill_id=skill.id))["data"]["items"][0]
        assert failed["status"] == "failed" and failed["failure"] == "invalid_report"
        with patch.object(run_history_analysis, "delay") as retry, django_capture_on_commit_callbacks(execute=True):
            assert _body(call(admin, "analysis_retry", "post", **params))["data"]["id"] == initial["id"]
        finding["evidence"] = [question, b.pk]
        client.invoke.return_value = SimpleNamespace(content=[{"type": "text", "text": json.dumps([finding])}])
        run_history_analysis(*queue.call_args.args)
        run_history_analysis(*retry.call_args.args)
        assert client.invoke.call_count == 2
    report = _body(call(admin, "analysis_report", **params))["data"]
    assert report["conversation_count"] == 2 and report["question_count"] == 4
    assert report["findings"][0]["evidence"][1] == {"session_id": second.session_id, "message_id": b.pk}
    pdf = call(admin, "analysis_report", **params, download="pdf")
    with fitz.open(stream=pdf.content, filetype="pdf") as doc:
        text = "".join(page.get_text() for page in doc)
    assert all(label in text for label in ("诊断报告", "需要改进", "补充排查步骤", f"#{b.pk}"))
    assert "第二个对话" not in text and "连接失败" not in text


def test_error_recovery_and_deleted_evidence(history, django_capture_on_commit_callbacks):
    from apps.opspilot.tasks.history_analysis import run_history_analysis

    skill, conv, question, _ = history
    user = _superuser()
    config = dict(skill_id=skill.pk, scope="sessions", session_ids=[conv.session_id], name="A", objective="overview", request_id=str(uuid.uuid4()))
    with patch.object(run_history_analysis, "delay", side_effect=ConnectionError()), django_capture_on_commit_callbacks(execute=True):
        pk = _body(call(user, "analyses", "post", **config))["data"]["id"]
    task = _body(call(user, "analyses", skill_id=skill.pk))["data"]["items"][0]
    assert task["failure"] == "dispatch_failed"
    history_data = _body(call(user, "admin_conversation_messages", session_id=conv.session_id, message_id=question))["data"]
    assert history_data.get("data", history_data)["messages"][0]["id"] == question
    Message.objects.filter(pk=question).delete()
    assert call(user, "admin_conversation_messages", session_id=conv.session_id, message_id=question).status_code == 404
    with patch.object(run_history_analysis, "delay") as queue, django_capture_on_commit_callbacks(execute=True):
        call(user, "analysis_retry", "post", skill_id=skill.pk, task_id=pk)
    with patch("apps.opspilot.tasks.history_analysis.analyze_turns") as model:
        run_history_analysis(*queue.call_args.args)
        model.assert_not_called()
    assert _body(call(user, "analyses", skill_id=skill.pk))["data"]["items"][0]["failure"] == "source_missing"


def test_preview_filters_and_limits(history):
    skill, conv, _, now = history
    user = _superuser()
    params = dict(skill_id=skill.id, scope="range", start=(now - timedelta(days=1)).isoformat(), end=(now + timedelta(days=1)).isoformat())
    for filters in ({"person": "nobody"}, {"channel_id": 987}):
        assert _body(call(user, "analysis_preview", "post", **params, **filters))["data"]["issue"] == "empty"
    assert _body(call(user, "analysis_preview", "post", **params, person="alice"))["data"]["conversation_count"] == 1
    Message.objects.create(conversation=conv, role="user", content="x" * 48001)
    assert _body(call(user, "analysis_preview", "post", **params))["data"]["issue"] == "too_large"
    assert call(user, "analyses", "post", **params, name="A", objective="overview", request_id=str(uuid.uuid4())).status_code == 400
    assert call(user, "analysis_preview", "post", **(params | {"end": params["start"]})).status_code == 400


def test_expired_worker_cannot_overwrite_retried_report(history, django_capture_on_commit_callbacks):
    from apps.opspilot.models import SkillHistoryAnalysis
    from apps.opspilot.tasks.history_analysis import run_history_analysis

    skill, conv, question, _ = history
    user = _superuser()
    config = dict(skill_id=skill.pk, scope="sessions", session_ids=[conv.session_id], name="A", objective="quality", request_id=str(uuid.uuid4()))
    with patch.object(run_history_analysis, "delay") as queue, django_capture_on_commit_callbacks(execute=True):
        pk = _body(call(user, "analyses", "post", **config))["data"]["id"]

    def produce(task, _turns):
        if task.attempt == 1:
            SkillHistoryAnalysis.objects.filter(pk=pk).update(updated_at=timezone.now() - timedelta(minutes=10))
            with patch.object(run_history_analysis, "delay") as retry, django_capture_on_commit_callbacks(execute=True):
                assert call(user, "analysis_retry", "post", skill_id=skill.id, task_id=pk).status_code == 200
            run_history_analysis(*retry.call_args.args)
        return [{"finding": f"第{task.attempt}次分析", "suggestion": "优化排查步骤", "evidence": [question]}]

    with patch("apps.opspilot.tasks.history_analysis.analyze_turns", side_effect=produce):
        run_history_analysis(*queue.call_args.args)
    report = _body(call(user, "analysis_report", skill_id=skill.id, task_id=pk))["data"]
    assert report["findings"][0]["finding"] == "第2次分析"


def test_channels_and_tasks_share_question_window_and_type_filter(history):
    skill, platform, _, now = history
    admin = _superuser()
    scope = dict(skill_id=skill.pk, scope="range", start=(now - timedelta(days=1)).isoformat(), end=(now + timedelta(days=1)).isoformat())
    selected_ids = []
    for session in ("workflow_a", "workflow_b", "workbench_c", "second_platform"):
        channel = _channel(skill, channel_type="platform", name="第二个发布渠道") if session == "second_platform" else None
        conv = _conv(skill, channel, session_id=session, external_user_id="流程用户" if channel is None else "bob", title="巡检")
        Message.objects.create(conversation=conv, role="user", content="问题")
        selected_ids.append(conv.session_id)
    outside = _conv(skill, _channel(skill, channel_type="web_chat"), session_id="old", external_user_id="other")
    late = Message.objects.create(conversation=outside, role="user", content="前一周的问题")
    Message.objects.filter(pk=late.pk).update(created_at=now - timedelta(days=7))
    Message.objects.create(conversation=outside, role="assistant", content="今天的回复")
    without_questions = _conv(skill, None, session_id="workflow_empty", external_user_id="流程用户", title="巡检")
    Message.objects.create(conversation=without_questions, role="assistant", content="回复")
    other = _skill(name="不可见")
    foreign = _conv(other, _channel(other, channel_type="feishu"), session_id="other_skill", external_user_id="bob")
    Message.objects.create(conversation=foreign, role="user", content="不可见")

    def channels(params):
        items = _body(call(admin, "analysis_channels", "post", **params))["data"]["items"]
        return {item["channel_type"]: item["conversation_count"] for item in items}

    assert channels(scope) == {"platform": 2, "workflow": 2, "workbench": 1}
    assert channels(scope | {"channel_id": platform.channel_id}) == {"platform": 1}
    assert channels(scope | {"person": "流程用户"}) == {"workflow": 2, "workbench": 1}
    assert channels(dict(skill_id=skill.pk, scope="sessions", title="巡检")) == {"platform": 1, "workflow": 2, "workbench": 1}
    assert channels(dict(skill_id=skill.pk, scope="sessions", title="不匹配")) == {}

    def preview(params):
        return _body(call(admin, "analysis_preview", "post", **params))["data"]

    assert preview(scope)["question_count"] == 4
    assert preview(scope | {"channel_types": []})["issue"] == "empty"
    assert preview(scope | {"channel_types": ["workbench", "workflow"]})["question_count"] == 3
    config = dict(name="按渠道分析", objective="overview", request_id=str(uuid.uuid4()))
    args = scope | {"channel_types": ["workflow"]} | config
    created = _body(call(admin, "analyses", "post", **args))["data"]
    assert created["question_count"] == 2 and created["scope"]["channel_types"] == ["workflow"]
    assert call(admin, "analyses", "post", **(args | {"channel_types": [], "request_id": str(uuid.uuid4())})).status_code == 400
    selected = dict(skill_id=skill.pk, scope="sessions", session_ids=selected_ids[:3])
    created = _body(call(admin, "analyses", "post", **selected, **(config | {"request_id": str(uuid.uuid4())})))["data"]
    assert created["question_count"] == 3 and set(created["scope"]["channel_types"]) == {"workflow", "workbench"}
    assert call(admin, "analysis_preview", "post", **(scope | {"channel_types": ["invalid"]})).status_code == 400
    result = _body(call(admin, "admin_conversations", skill_id=skill.pk, channel_types="workflow,workbench", title="巡检", page_size=2))
    data = result["data"].get("data", result["data"])
    assert data["count"] == 3
    assert {item["session_id"] for item in data["items"]} <= set(selected_ids[:3])
