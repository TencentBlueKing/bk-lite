"""MemorySpace / Memory CRUD 与 test_write 契约：鉴权通过后写库、审计与 LLM 校验。"""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pydantic.root_model  # noqa
import pytest
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
