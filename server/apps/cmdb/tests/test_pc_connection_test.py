# -*- coding: utf-8 -*-
"""PC 连接测试 API 合同测试。

锁定：
- 连接测试不创建 CollectModels、不写图实例；
- 通过 STARGAZER_URL 的 HTTP debug 端点调用，超时固定 15 秒，不新增 NATS subject；
- 成功返回 {success, os_type, inst_name, hardware_uuid|serial_number}；
- 失败返回稳定错误码 + 固定中文文案，不透传 Stargazer 原始细节；
- 密码/私钥/密码短语只出现在转发 body，绝不进入响应 message；
- 编辑场景掩码凭据按 task_id 解密（需对象权限），非 PC 任务拒绝。
"""
import json

import pytest
import requests as requests_lib
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.services.collect_tool_service import MASKED_PASSWORD
from apps.cmdb.tests.test_collect_views_actions import _bypass_permission
from apps.cmdb.views.collect import CollectModelViewSet
from apps.core.exceptions.base_app_exception import BaseAppException

WINDOWS_REQUEST = {
    "os_type": "windows",
    "host": "10.0.0.8",
    "access_point_id": "node-1",
    "credential": {
        "username": "ACME\\alice",
        "password": "real-secret",
        "port": 5986,
    },
    "winrm_scheme": "https",
    "winrm_transport": "ntlm",
    "winrm_cert_validation": False,
}

STARGAZER_OK = {
    "success": True,
    "os_type": "windows",
    "inst_name": "WIN-4C4C4544-0038-5810-805A-CAC04F595832",
    "hardware_uuid": "4C4C4544-0038-5810-805A-CAC04F595832",
    "serial_number": "",
}


@pytest.fixture
def superuser(authenticated_user):
    u = authenticated_user
    u.is_superuser = True
    u.group_list = [{"id": 1}]
    u.roles = ["admin"]
    u.domain = "domain.com"
    return u


def _data(response):
    return json.loads(response.content)["data"]


def _test_connection(user, payload):
    factory = APIRequestFactory()
    request = factory.post("/x/", data=payload, format="json")
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)
    return CollectModelViewSet.as_view({"post": "pc_test_connection"})(request)


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def _task(name, model_id="pc", credential=None):
    return CollectModels.objects.create(
        name=name,
        task_type=CollectPluginTypes.HOST,
        driver_type=CollectDriverTypes.JOB,
        model_id=model_id,
        cycle_value_type="cycle",
        team=[1],
        credential=credential,
    )


@pytest.mark.django_db
def test_pc_connection_test_does_not_create_task_or_graph_instance(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    calls = {}

    def fake_post(url, json=None, timeout=None, **kwargs):
        calls["url"] = url
        calls["json"] = json
        calls["timeout"] = timeout
        return _FakeResponse(STARGAZER_OK)

    monkeypatch.setattr("apps.cmdb.services.pc_connection_test.requests.post", fake_post)

    before = CollectModels.objects.count()
    response = _test_connection(superuser, WINDOWS_REQUEST)

    assert response.status_code == 200
    assert CollectModels.objects.count() == before
    assert _data(response)["success"] is True
    assert _data(response)["inst_name"].startswith("WIN-")
    assert calls["timeout"] == 15
    assert calls["url"].endswith("/api/collect/pc_test_connection")
    # 接入点作为 node_id 下发给 Stargazer 路由真实执行器
    assert calls["json"]["node_id"] == "node-1"
    assert calls["json"]["os_type"] == "windows"


@pytest.mark.django_db
def test_pc_connection_test_forwards_secret_only_in_body(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    calls = {}

    def fake_post(url, json=None, timeout=None, **kwargs):
        calls["json"] = json
        return _FakeResponse(STARGAZER_OK)

    monkeypatch.setattr("apps.cmdb.services.pc_connection_test.requests.post", fake_post)

    response = _test_connection(superuser, WINDOWS_REQUEST)

    assert calls["json"]["password"] == "real-secret"
    assert "real-secret" not in response.content.decode()


@pytest.mark.django_db
def test_pc_connection_test_timeout_maps_to_stable_error(superuser, monkeypatch):
    _bypass_permission(monkeypatch)

    def fake_post(url, json=None, timeout=None, **kwargs):
        raise requests_lib.Timeout()

    monkeypatch.setattr("apps.cmdb.services.pc_connection_test.requests.post", fake_post)

    response = _test_connection(superuser, WINDOWS_REQUEST)

    assert response.status_code == 200
    data = _data(response)
    assert data["success"] is False
    assert data["error_code"] == "SCRIPT_TIMEOUT"
    assert data["message"]
    assert "real-secret" not in response.content.decode()


@pytest.mark.django_db
def test_pc_connection_test_stargazer_error_code_with_fixed_message(superuser, monkeypatch):
    _bypass_permission(monkeypatch)

    def fake_post(url, json=None, timeout=None, **kwargs):
        return _FakeResponse(
            {"success": False, "error_code": "WINRM_AUTH_FAILED", "message": "raw detail with real-secret"}
        )

    monkeypatch.setattr("apps.cmdb.services.pc_connection_test.requests.post", fake_post)

    response = _test_connection(superuser, WINDOWS_REQUEST)

    data = _data(response)
    assert data["success"] is False
    assert data["error_code"] == "WINRM_AUTH_FAILED"
    # 不透传 Stargazer 原始 message（可能夹带敏感细节），只给固定中文文案
    assert "raw detail" not in response.content.decode()
    assert "real-secret" not in response.content.decode()


@pytest.mark.django_db
def test_pc_connection_test_unreachable_stargazer(superuser, monkeypatch):
    _bypass_permission(monkeypatch)

    def fake_post(url, json=None, timeout=None, **kwargs):
        raise requests_lib.ConnectionError("refused")

    monkeypatch.setattr("apps.cmdb.services.pc_connection_test.requests.post", fake_post)

    response = _test_connection(superuser, WINDOWS_REQUEST)

    data = _data(response)
    assert data["success"] is False
    assert data["error_code"] == "TARGET_UNREACHABLE"


@pytest.mark.django_db
def test_pc_connection_test_masked_credential_decrypted_by_task(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    monkeypatch.setattr(CollectModelViewSet, "get_has_permission", lambda *a, **k: True)
    task = _task("pc-task", credential={"username": "ACME\\alice", "password": "real-secret", "port": 5986})
    calls = {}

    def fake_post(url, json=None, timeout=None, **kwargs):
        calls["json"] = json
        return _FakeResponse(STARGAZER_OK)

    monkeypatch.setattr("apps.cmdb.services.pc_connection_test.requests.post", fake_post)

    payload = dict(WINDOWS_REQUEST)
    payload["task_id"] = task.id
    payload["credential"] = {"username": "ACME\\alice", "password": MASKED_PASSWORD, "port": 5986}
    response = _test_connection(superuser, payload)

    assert response.status_code == 200
    assert calls["json"]["password"] == "real-secret"


@pytest.mark.django_db
def test_pc_connection_test_masked_credential_without_permission_denied(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    monkeypatch.setattr(CollectModelViewSet, "get_has_permission", lambda *a, **k: False)
    task = _task("pc-task", credential={"username": "u", "password": "real-secret"})

    payload = dict(WINDOWS_REQUEST)
    payload["task_id"] = task.id
    payload["credential"] = {"username": "u", "password": MASKED_PASSWORD}
    with pytest.raises(BaseAppException):
        _test_connection(superuser, payload)


@pytest.mark.django_db
def test_pc_connection_test_masked_credential_with_non_pc_task_rejected(superuser, monkeypatch):
    _bypass_permission(monkeypatch)
    monkeypatch.setattr(CollectModelViewSet, "get_has_permission", lambda *a, **k: True)
    task = _task("host-task", model_id="host", credential={"username": "u", "password": "real-secret"})

    payload = dict(WINDOWS_REQUEST)
    payload["task_id"] = task.id
    payload["credential"] = {"username": "u", "password": MASKED_PASSWORD}
    with pytest.raises(BaseAppException, match="PC"):
        _test_connection(superuser, payload)


@pytest.mark.django_db
def test_pc_connection_test_invalid_os_type_rejected(superuser, monkeypatch):
    _bypass_permission(monkeypatch)

    payload = dict(WINDOWS_REQUEST)
    payload["os_type"] = "linux"
    with pytest.raises(BaseAppException):
        _test_connection(superuser, payload)
