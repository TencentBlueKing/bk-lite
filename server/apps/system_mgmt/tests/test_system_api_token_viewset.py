"""SystemAPIToken 管理 API：发放 / 列表 / PATCH 元数据 / 吊销 / 独立权限位。

对照 specs/changes/openapi-system-token：系统令牌走系统管理 CRUD，权限位独立于
个人 api_secret_key，明文仅创建响应返回一次，发放与吊销写操作日志且不含令牌值。
"""

import json
import types
from datetime import timedelta
from pathlib import Path

import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.system_mgmt.models import OperationLog, SystemAPIToken
from apps.system_mgmt.viewset.system_api_token_viewset import SystemAPITokenViewSet

factory = APIRequestFactory()
BASE_PATH = "/system_mgmt/system_api_token/"


def _user(perms, is_superuser=False):
    return types.SimpleNamespace(
        username="sys-token-admin",
        domain="domain.com",
        locale="en",
        is_superuser=is_superuser,
        is_authenticated=True,
        permission={"system-manager": set(perms)},
    )


def _call(method, action, user, *, pk=None, data=None):
    path = BASE_PATH if pk is None else f"{BASE_PATH}{pk}/"
    factory_method = getattr(factory, method)
    kwargs = {}
    if data is not None:
        kwargs["data"] = data
        kwargs["format"] = "json"
    request = factory_method(path, **kwargs)
    force_authenticate(request, user=user)
    view = SystemAPITokenViewSet.as_view({method: action})
    if pk is None:
        return view(request)
    return view(request, pk=pk)


def _store(**kwargs):
    secret = SystemAPIToken.generate_secret()
    token = SystemAPIToken.objects.create(
        system_id=kwargs.get("system_id", "itsm"),
        name=kwargs.get("name", "ITSM 异步节点"),
        secret_hash=SystemAPIToken.hash_secret(secret),
        scope=kwargs.get("scope", {"mode": "all"}),
        enabled=kwargs.get("enabled", True),
        expires_at=kwargs.get("expires_at"),
        created_by=kwargs.get("created_by", "admin"),
    )
    return token, secret


def test_system_manager_setting_includes_independent_system_api_secret_bits():
    payload = json.loads(Path("support-files/system_mgmt/menus/system-manager.json").read_text(encoding="utf-8"))
    setting = next(menu for menu in payload["menus"] if menu["name"] == "Setting")
    child = next(item for item in setting["children"] if item["id"] == "system_api_secret")
    assert child["operation"] == ["View", "Add", "Edit", "Delete"]
    for role in payload["roles"]:
        if role["name"] == "admin":
            continue
        assert not any(name.startswith("system_api_secret-") for name in role["menus"])


@pytest.mark.django_db
def test_list_denied_without_view_permission():
    response = _call("get", "list", _user(set()))
    assert response.status_code == 403


@pytest.mark.django_db
def test_list_denied_with_only_personal_api_secret_permission():
    response = _call("get", "list", _user({"api_secret_key-View"}))
    assert response.status_code == 403


@pytest.mark.django_db
def test_create_denied_without_add_permission():
    response = _call("post", "create", _user({"system_api_secret-View"}), data={"system_id": "itsm"})
    assert response.status_code == 403


@pytest.mark.django_db
def test_create_issues_plaintext_once_and_stores_hash():
    response = _call(
        "post",
        "create",
        _user({"system_api_secret-Add"}),
        data={
            "system_id": "itsm",
            "name": "ITSM 异步节点",
            "scope": {"mode": "all"},
        },
    )
    assert response.status_code == 201, response.data
    plaintext = response.data["api_secret"]
    assert plaintext.startswith("bksys_")
    assert len(plaintext) == len("bksys_") + 64
    assert "secret_hash" not in response.data
    stored = SystemAPIToken.objects.get(pk=response.data["id"])
    assert stored.secret_hash == SystemAPIToken.hash_secret(plaintext)
    assert stored.secret_hash != plaintext
    assert stored.system_id == "itsm"
    assert stored.name == "ITSM 异步节点"
    assert stored.scope == {"mode": "all"}
    assert stored.created_by == "sys-token-admin"
    assert stored.created_by_domain == "domain.com"


@pytest.mark.django_db
def test_create_allows_multiple_tokens_for_same_system_id():
    user = _user({"system_api_secret-Add"})
    first = _call("post", "create", user, data={"system_id": "itsm", "name": "current", "scope": {"mode": "all"}})
    second = _call("post", "create", user, data={"system_id": "itsm", "name": "next", "scope": {"mode": "all"}})
    assert first.status_code == 201
    assert second.status_code == 201
    assert SystemAPIToken.objects.filter(system_id="itsm").count() == 2
    assert first.data["api_secret"] != second.data["api_secret"]


@pytest.mark.django_db
def test_create_requires_name():
    response = _call(
        "post",
        "create",
        _user({"system_api_secret-Add"}),
        data={"system_id": "itsm"},
    )
    assert response.status_code == 400
    assert "name" in response.data


@pytest.mark.django_db
def test_create_requires_scope():
    response = _call(
        "post",
        "create",
        _user({"system_api_secret-Add"}),
        data={"system_id": "itsm", "name": "ITSM"},
    )
    assert response.status_code == 400
    assert "scope" in response.data


@pytest.mark.django_db
def test_create_rejects_duplicate_name_for_same_system_id():
    user = _user({"system_api_secret-Add"})
    first = _call("post", "create", user, data={"system_id": "itsm", "name": "current", "scope": {"mode": "all"}})
    second = _call("post", "create", user, data={"system_id": "itsm", "name": "current", "scope": {"mode": "all"}})
    assert first.status_code == 201
    assert second.status_code == 400
    assert "name" in second.data


@pytest.mark.django_db
def test_create_ignores_client_supplied_secret_hash():
    response = _call(
        "post",
        "create",
        _user({"system_api_secret-Add"}),
        data={"system_id": "itsm", "name": "ITSM", "secret_hash": "sha256$forged", "scope": {"mode": "all"}},
    )
    assert response.status_code == 201, response.data
    stored = SystemAPIToken.objects.get(pk=response.data["id"])
    assert stored.secret_hash != "sha256$forged"
    assert stored.secret_hash == SystemAPIToken.hash_secret(response.data["api_secret"])


@pytest.mark.django_db
@pytest.mark.parametrize("system_id", ["ITSM", "itsm_openapi", "1itsm", "", "a" * 33])
def test_create_rejects_invalid_system_id(system_id):
    response = _call(
        "post",
        "create",
        _user({"system_api_secret-Add"}),
        data={"system_id": system_id, "name": "bad"},
    )
    assert response.status_code == 400


@pytest.mark.django_db
@pytest.mark.parametrize(
    "scope",
    [
        "cmdb",
        ["asset_info-View"],
        {"cmdb": "asset_info-View"},
        {"cmdb": ["asset_info-View"]},
        {"mode": "allowlist", "endpoints": []},
    ],
)
def test_create_rejects_invalid_scope(scope):
    response = _call(
        "post",
        "create",
        _user({"system_api_secret-Add"}),
        data={"system_id": "itsm", "name": "ITSM", "scope": scope},
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_list_returns_preview_without_secret():
    token, secret = _store()
    response = _call("get", "list", _user({"system_api_secret-View"}))
    assert response.status_code == 200
    rows = response.data["items"] if isinstance(response.data, dict) else response.data
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == token.pk
    assert row["system_id"] == "itsm"
    assert row["name"] == "ITSM 异步节点"
    assert row["api_secret_preview"] == "bksys_********"
    assert row["scope"] == {"mode": "all"}
    assert row["enabled"] is True
    assert "api_secret" not in row
    assert "secret_hash" not in row
    assert secret not in json.dumps(row)


@pytest.mark.django_db
def test_put_rejected():
    token, _ = _store()
    response = _call(
        "put",
        "update",
        _user({"system_api_secret-Edit"}),
        pk=token.pk,
        data={"name": "replaced", "system_id": "itsm"},
    )
    body = json.loads(response.content)
    assert body["result"] is False
    token.refresh_from_db()
    assert token.name == "ITSM 异步节点"


@pytest.mark.django_db
def test_patch_updates_metadata_without_rotating_secret():
    token, secret = _store()
    original_hash = token.secret_hash
    expires = timezone.now() + timedelta(days=30)
    response = _call(
        "patch",
        "partial_update",
        _user({"system_api_secret-Edit"}),
        pk=token.pk,
        data={
            "name": "轮转中",
            "expires_at": expires.isoformat(),
            "scope": {"mode": "allowlist", "endpoints": ["GET cmdb/classifications"]},
        },
    )
    assert response.status_code == 200, response.data
    assert response.data["name"] == "轮转中"
    assert response.data["scope"] == {"mode": "allowlist", "endpoints": ["GET cmdb/classifications"]}
    assert "api_secret" not in response.data
    token.refresh_from_db()
    assert token.secret_hash == original_hash
    assert token.name == "轮转中"
    assert SystemAPIToken.find_live_by_secret(secret) == token


@pytest.mark.django_db
def test_patch_does_not_change_system_id():
    token, _ = _store()
    response = _call(
        "patch",
        "partial_update",
        _user({"system_api_secret-Edit"}),
        pk=token.pk,
        data={"system_id": "other"},
    )
    assert response.status_code == 200, response.data
    token.refresh_from_db()
    assert token.system_id == "itsm"


@pytest.mark.django_db
def test_patch_disable_revokes_immediately():
    token, secret = _store()
    response = _call(
        "patch",
        "partial_update",
        _user({"system_api_secret-Edit"}),
        pk=token.pk,
        data={"enabled": False},
    )
    assert response.status_code == 200
    assert SystemAPIToken.find_live_by_secret(secret) is None
    token.refresh_from_db()
    assert token.enabled is False


@pytest.mark.django_db
def test_delete_revokes_immediately():
    token, secret = _store()
    response = _call("delete", "destroy", _user({"system_api_secret-Delete"}), pk=token.pk)
    assert response.status_code in (200, 204)
    assert not SystemAPIToken.objects.filter(pk=token.pk).exists()
    assert SystemAPIToken.find_live_by_secret(secret) is None


def _assert_log_has_no_secret(log, secret=None):
    blob = json.dumps({"summary": log.summary, "detail": log.detail, "target_id": log.target_id}, ensure_ascii=False)
    assert "bksys_" not in blob
    assert "sha256$" not in blob
    if secret:
        assert secret not in blob


@pytest.mark.django_db
def test_create_writes_issue_operation_log_without_secret():
    response = _call(
        "post",
        "create",
        _user({"system_api_secret-Add"}),
        data={"system_id": "itsm", "name": "ITSM", "scope": {"mode": "all"}},
    )
    assert response.status_code == 201, response.data
    log = OperationLog.objects.get(target_type="system_api_token", action_type="create")
    assert log.username == "sys-token-admin"
    assert log.app == "system-manager"
    assert log.target_id == str(response.data["id"])
    assert log.summary == "创建系统令牌: ITSM (itsm)"
    assert log.detail == {"kind": "system", "name": "ITSM", "system_id": "itsm"}
    _assert_log_has_no_secret(log, response.data["api_secret"])


@pytest.mark.django_db
def test_delete_writes_revoke_operation_log_without_secret():
    token, secret = _store()
    response = _call("delete", "destroy", _user({"system_api_secret-Delete"}), pk=token.pk)
    assert response.status_code in (200, 204)
    log = OperationLog.objects.get(target_type="system_api_token", action_type="delete")
    assert log.username == "sys-token-admin"
    assert log.summary == f"删除系统令牌: {token.name} ({token.system_id})"
    assert log.detail == {"kind": "system", "name": token.name, "system_id": "itsm"}
    assert log.target_id == str(token.pk)
    _assert_log_has_no_secret(log, secret)


@pytest.mark.django_db
def test_patch_writes_update_operation_log():
    token, secret = _store()
    response = _call(
        "patch",
        "partial_update",
        _user({"system_api_secret-Edit"}),
        pk=token.pk,
        data={"enabled": False},
    )
    assert response.status_code == 200
    log = OperationLog.objects.get(target_type="system_api_token", action_type="update")
    assert log.summary == f"更新系统令牌: {token.name} ({token.system_id})"
    assert log.detail == {"kind": "system", "name": token.name, "system_id": "itsm"}
    _assert_log_has_no_secret(log, secret)
