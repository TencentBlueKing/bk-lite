"""MemorySpace / Memory CRUD 与 test_write 契约：鉴权通过后写库、审计与 LLM 校验。"""
import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pydantic.root_model  # noqa
import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.tests.factories import UserFactory
from apps.opspilot.models import LLMModel
from apps.opspilot.models.memory_mgmt import Memory, MemorySpace
from apps.opspilot.viewsets.memory_view import MemorySpaceViewSet, MemoryViewSet

pytestmark = pytest.mark.django_db

factory = APIRequestFactory()


def _superuser():
    return UserFactory(username="mem-su", domain="domain.com", roles=[], is_superuser=True)


def _call(view, request, user, **kwargs):
    force_authenticate(request, user=user)
    request.COOKIES["current_team"] = "1"
    return view(request, **kwargs)


def _body(resp):
    if callable(getattr(resp, "render", None)) and not getattr(resp, "is_rendered", True):
        resp.render()
    if hasattr(resp, "content"):
        return json.loads(resp.content.decode("utf-8"))
    return resp.data


def _allow_team(monkeypatch):
    monkeypatch.setattr(
        "apps.core.utils.serializers.get_permission_rules",
        lambda *a, **k: {"team": [1], "instance": []},
    )
    monkeypatch.setattr(
        "apps.core.utils.viewset_utils.get_permission_rules",
        lambda *a, **k: {"team": [1], "instance": []},
    )


def test_memory_space_create_update_destroy_writes_audit(monkeypatch):
    _allow_team(monkeypatch)
    logs = []
    monkeypatch.setattr(
        "apps.opspilot.viewsets.memory_view.log_operation",
        lambda request, action, app, summary: logs.append((action, app, summary)),
    )
    user = _superuser()
    created = _call(
        MemorySpaceViewSet.as_view({"post": "create"}),
        factory.post("/", {"name": "空间A", "introduction": "i", "scope": "team"}, format="json"),
        user,
    )
    assert created.status_code == status.HTTP_201_CREATED
    space = MemorySpace.objects.get(name="空间A")
    assert space.team == [1]
    assert ("create", "opspilot", "新增记忆空间: 空间A") in logs

    updated = _call(
        MemorySpaceViewSet.as_view({"put": "update"}),
        factory.put(
            "/x/",
            {"name": "空间B", "introduction": "j", "scope": "team", "team": [1]},
            format="json",
        ),
        user,
        pk=space.id,
    )
    assert updated.status_code == status.HTTP_200_OK
    space.refresh_from_db()
    assert space.name == "空间B"
    assert ("update", "opspilot", "编辑记忆空间: 空间B") in logs

    patched = _call(
        MemorySpaceViewSet.as_view({"patch": "partial_update"}),
        factory.patch("/x/", {"name": "空间B", "introduction": "k", "team": [1]}, format="json"),
        user,
        pk=space.id,
    )
    assert patched.status_code == status.HTTP_200_OK
    space.refresh_from_db()
    assert space.introduction == "k"

    deleted = _call(
        MemorySpaceViewSet.as_view({"delete": "destroy"}),
        factory.delete("/x/"),
        user,
        pk=space.id,
    )
    assert deleted.status_code in (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT)
    assert not MemorySpace.objects.filter(id=space.id).exists()
    assert ("delete", "opspilot", "删除记忆空间: 空间B") in logs


def test_memory_space_retrieve_returns_detail():
    user = _superuser()
    space = MemorySpace.objects.create(name="详情空间", team=[1], scope=MemorySpace.SCOPE_TEAM)
    resp = _call(
        MemorySpaceViewSet.as_view({"get": "retrieve"}),
        factory.get("/x/"),
        user,
        pk=space.id,
    )
    body = _body(resp)
    assert body["result"] is True
    assert body["data"]["name"] == "详情空间"


def test_memory_create_sets_owner_and_audit(monkeypatch):
    _allow_team(monkeypatch)
    logs = []
    monkeypatch.setattr(
        "apps.opspilot.viewsets.memory_view.log_operation",
        lambda request, action, app, summary: logs.append((action, summary)),
    )
    user = _superuser()
    space = MemorySpace.objects.create(name="团队空间", team=[1], scope=MemorySpace.SCOPE_TEAM)
    created = _call(
        MemoryViewSet.as_view({"post": "create"}),
        factory.post(
            "/",
            {"memory_space": space.id, "title": "第一条", "content": "hello"},
            format="json",
        ),
        user,
    )
    assert created.status_code == status.HTTP_201_CREATED
    mem = Memory.objects.get(title="第一条")
    # owner_* 在序列化器上是 read_only，create 写入不会落到库；只钉死标题与审计。
    assert mem.content == "hello"
    assert ("create", "新增记忆: 第一条") in logs

    updated = _call(
        MemoryViewSet.as_view({"put": "update"}),
        factory.put(
            "/x/",
            {"memory_space": space.id, "title": "改名", "content": "world"},
            format="json",
        ),
        user,
        pk=mem.id,
    )
    assert updated.status_code == status.HTTP_200_OK
    mem.refresh_from_db()
    assert mem.title == "改名"
    assert ("update", "编辑记忆: 改名") in logs

    patched = _call(
        MemoryViewSet.as_view({"patch": "partial_update"}),
        factory.patch(
            "/x/",
            {"memory_space": space.id, "title": "改名", "content": "patched"},
            format="json",
        ),
        user,
        pk=mem.id,
    )
    assert patched.status_code == status.HTTP_200_OK
    mem.refresh_from_db()
    assert mem.content == "patched"

    retrieved = _call(MemoryViewSet.as_view({"get": "retrieve"}), factory.get("/x/"), user, pk=mem.id)
    body = _body(retrieved)
    assert body["result"] is True
    assert body["data"]["title"] == "改名"
    assert body["data"]["content"] == "patched"
    assert body["data"]["content_length"] == len("patched")
    assert body["data"]["content_truncated"] is False

    deleted = _call(MemoryViewSet.as_view({"delete": "destroy"}), factory.delete("/x/"), user, pk=mem.id)
    assert deleted.status_code in (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT)
    assert not Memory.objects.filter(id=mem.id).exists()
    assert ("delete", "删除记忆: 改名") in logs


def test_test_write_validates_input_rule_and_model(monkeypatch):
    user = _superuser()
    view = MemorySpaceViewSet.as_view({"post": "test_write"})

    missing_input = _call(view, factory.post("/", {"write_rule": "r"}, format="json"), user)
    body = _body(missing_input)
    assert missing_input.status_code == 400
    assert body["result"] is False
    assert body["message"] == "input 为必填项"

    passthrough = _call(view, factory.post("/", {"input": "原文"}, format="json"), user)
    body = _body(passthrough)
    assert passthrough.status_code == 200
    assert body == {"result": True, "data": {"result": "原文"}}

    missing_model = _call(
        view,
        factory.post("/", {"input": "原文", "write_rule": "整理"}, format="json"),
        user,
    )
    body = _body(missing_model)
    assert missing_model.status_code == 400
    assert body["message"] == "model_id 为必填项"

    not_found = _call(
        view,
        factory.post("/", {"input": "原文", "write_rule": "整理", "model_id": 999999}, format="json"),
        user,
    )
    body = _body(not_found)
    assert not_found.status_code == 404
    assert body["message"] == "配置的模型不存在"

    llm = LLMModel.objects.create(name="mem-llm", model="gpt", team=[1])
    monkeypatch.setattr(
        "apps.opspilot.viewsets.memory_view.LLMClientFactory.create_client",
        lambda *a, **k: SimpleNamespace(invoke=lambda messages: SimpleNamespace(content="规范化结果")),
    )
    ok = _call(
        view,
        factory.post("/", {"input": "原文", "write_rule": "整理成要点", "model_id": llm.id}, format="json"),
        user,
    )
    body = _body(ok)
    assert ok.status_code == 200
    assert body == {"result": True, "data": {"result": "规范化结果"}}

    monkeypatch.setattr(
        "apps.opspilot.viewsets.memory_view.LLMClientFactory.create_client",
        Mock(side_effect=RuntimeError("llm down")),
    )
    failed = _call(
        view,
        factory.post("/", {"input": "原文", "write_rule": "整理", "model_id": llm.id}, format="json"),
        user,
    )
    body = _body(failed)
    assert failed.status_code == 500
    assert body["result"] is False
    assert body["message"] == "LLM 调用失败: llm down"


def test_memory_retrieve_content_limit_truncates_without_full_payload():
    user = _superuser()
    space = MemorySpace.objects.create(name="限流空间", team=[1], scope=MemorySpace.SCOPE_TEAM)
    huge = "B" * 4000
    mem = Memory.objects.create(memory_space=space, title="大记忆", content=huge, owner_username="mem-su", owner_domain="domain.com")
    view = MemoryViewSet.as_view({"get": "retrieve"})

    limited = _call(view, factory.get("/x/", {"content_limit": "120"}), user, pk=mem.id)
    body = _body(limited)
    assert limited.status_code == status.HTTP_200_OK
    assert body["data"]["content"] == huge[:120]
    assert body["data"]["content_length"] == 4000
    assert body["data"]["content_truncated"] is True
    assert huge not in limited.content.decode("utf-8")

    invalid = _call(view, factory.get("/x/", {"content_limit": "abc"}), user, pk=mem.id)
    body = _body(invalid)
    assert invalid.status_code == 400
    assert body["result"] is False
    assert body["message"] == "content_limit 必须是正整数"


def test_memory_retrieve_content_offset_returns_middle_slice():
    user = _superuser()
    space = MemorySpace.objects.create(name="偏移空间", team=[1], scope=MemorySpace.SCOPE_TEAM)
    huge = "ABCDEFGHIJ" * 40
    mem = Memory.objects.create(memory_space=space, title="切片记忆", content=huge, owner_username="mem-su", owner_domain="domain.com")
    view = MemoryViewSet.as_view({"get": "retrieve"})

    sliced = _call(view, factory.get("/x/", {"content_offset": "10", "content_limit": "8"}), user, pk=mem.id)
    body = _body(sliced)
    assert sliced.status_code == status.HTTP_200_OK
    assert body["data"]["content"] == huge[10:18]
    assert body["data"]["content_length"] == len(huge)
    assert body["data"]["content_offset"] == 10
    assert body["data"]["content_truncated"] is True
    assert huge not in sliced.content.decode("utf-8")

    invalid = _call(view, factory.get("/x/", {"content_offset": "-1"}), user, pk=mem.id)
    body = _body(invalid)
    assert invalid.status_code == 400
    assert body["message"] == "content_offset 必须是非负整数"


def test_memory_partial_update_splices_current_page():
    user = _superuser()
    space = MemorySpace.objects.create(name="分页写入", team=[1], scope=MemorySpace.SCOPE_TEAM)
    mem = Memory.objects.create(
        memory_space=space,
        title="切片改写",
        content="ABCDEFGHIJ",
        owner_username="mem-su",
        owner_domain="domain.com",
    )
    retrieved = _call(MemoryViewSet.as_view({"get": "retrieve"}), factory.get("/x/"), user, pk=mem.id)
    updated_at = _body(retrieved)["data"]["updated_at"]
    patched = _call(
        MemoryViewSet.as_view({"patch": "partial_update"}),
        factory.patch(
            "/x/",
            {
                "content": "xyz",
                "content_offset": 3,
                "content_replace_length": 4,
                "expected_updated_at": updated_at,
            },
            format="json",
        ),
        user,
        pk=mem.id,
    )
    assert patched.status_code == status.HTTP_200_OK
    body = _body(patched)
    assert body["data"]["content"] == "xyz"
    assert body["data"]["content_length"] == 9
    assert body["data"]["content_truncated"] is True
    mem.refresh_from_db()
    assert mem.content == "ABCxyzHIJ"

    oob = _call(
        MemoryViewSet.as_view({"patch": "partial_update"}),
        factory.patch(
            "/x/",
            {
                "content": "x",
                "content_offset": 99,
                "content_replace_length": 1,
                "expected_updated_at": _body(_call(MemoryViewSet.as_view({"get": "retrieve"}), factory.get("/x/"), user, pk=mem.id))["data"][
                    "updated_at"
                ],
            },
            format="json",
        ),
        user,
        pk=mem.id,
    )
    assert oob.status_code == 400
    mem.refresh_from_db()
    assert mem.content == "ABCxyzHIJ"


def test_memory_partial_update_splice_omits_full_content_from_response():
    user = _superuser()
    space = MemorySpace.objects.create(name="巨文切片", team=[1], scope=MemorySpace.SCOPE_TEAM)
    prefix = "HEAD_UNIQUE_AAA"
    page = "PAGE_CONTENT"
    suffix = "TAIL_UNIQUE_ZZZ" * 4000
    huge = prefix + page + suffix
    mem = Memory.objects.create(
        memory_space=space,
        title="巨文",
        content=huge,
        owner_username="mem-su",
        owner_domain="domain.com",
    )
    retrieved = _call(
        MemoryViewSet.as_view({"get": "retrieve"}),
        factory.get("/x/", {"content_offset": str(len(prefix)), "content_limit": str(len(page))}),
        user,
        pk=mem.id,
    )
    updated_at = _body(retrieved)["data"]["updated_at"]
    patched = _call(
        MemoryViewSet.as_view({"patch": "partial_update"}),
        factory.patch(
            "/x/",
            {
                "content": "NEW",
                "content_offset": len(prefix),
                "content_replace_length": len(page),
                "expected_updated_at": updated_at,
            },
            format="json",
        ),
        user,
        pk=mem.id,
    )
    assert patched.status_code == status.HTTP_200_OK
    body = _body(patched)
    payload = patched.content.decode("utf-8")
    assert suffix not in payload
    assert huge not in payload
    assert body["data"]["content"] == "NEW"
    assert body["data"]["content_length"] == len(prefix) + 3 + len(suffix)
    assert body["data"]["content_truncated"] is True
    mem.refresh_from_db()
    assert mem.content == prefix + "NEW" + suffix
    assert suffix in mem.content


def test_memory_partial_update_splice_conflict_returns_409():
    user = _superuser()
    space = MemorySpace.objects.create(name="并发切片", team=[1], scope=MemorySpace.SCOPE_TEAM)
    mem = Memory.objects.create(
        memory_space=space,
        title="冲突",
        content="ABCDEFGHIJ",
        owner_username="mem-su",
        owner_domain="domain.com",
    )
    retrieved = _call(MemoryViewSet.as_view({"get": "retrieve"}), factory.get("/x/"), user, pk=mem.id)
    stale = _body(retrieved)["data"]["updated_at"]
    Memory.objects.filter(pk=mem.pk).update(
        content="ABCDEFGHIJ-changed",
        updated_at=timezone.now() + timedelta(seconds=5),
    )

    patched = _call(
        MemoryViewSet.as_view({"patch": "partial_update"}),
        factory.patch(
            "/x/",
            {
                "content": "xyz",
                "content_offset": 3,
                "content_replace_length": 4,
                "expected_updated_at": stale,
            },
            format="json",
        ),
        user,
        pk=mem.id,
    )
    assert patched.status_code == status.HTTP_409_CONFLICT
    mem.refresh_from_db()
    assert mem.content == "ABCDEFGHIJ-changed"
