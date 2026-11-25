"""OpenAPI 调用日志读侧：全量可见、筛选与 Excel 导出。"""

from datetime import timedelta
from io import BytesIO

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone
from openpyxl import load_workbook
from rest_framework.test import APIClient

from apps.base.models import User as BaseUser
from apps.core.openapi.testing import create_api_tenant
from apps.system_mgmt.models import Group, OpenAPICallLog
from apps.system_mgmt.models import User as SystemUser

pytestmark = pytest.mark.django_db

V = "/api/v1/system_mgmt"


def _items(resp):
    data = resp.json()["data"]
    if isinstance(data, dict):
        return data.get("items") or []
    return data


def _ensure_group(team_id):
    Group.objects.get_or_create(id=team_id, defaults={"name": f"team-{team_id}"})


def _bind_system_user(user, team_id):
    SystemUser.objects.update_or_create(
        username=user.username,
        domain=user.domain,
        defaults={
            "display_name": user.username,
            "email": f"{user.username}@example.com",
            "password": "x",
            "group_list": [team_id],
        },
    )


def _client_for(user, team_id, *, is_superuser=False, permission=None):
    user.is_superuser = is_superuser
    user.save()
    user.group_list = [{"id": team_id}]
    user.permission = permission or {"system-manager": {"audit_log-View"}}
    client = APIClient()
    client.force_authenticate(user=user)
    client.cookies["current_team"] = str(team_id)
    return client


def _log(**over):
    defaults = {
        "source_ip": "10.0.0.1",
        "username": "alice",
        "credential_type": "api_token",
        "token_name": "alice-key",
        "system_id": "",
        "team_id": 1,
        "api_kind": OpenAPICallLog.API_KIND_INTERNAL,
        "method": "GET",
        "path": "/openapi/v1/patch-mgmt/module-data",
        "http_status": 200,
        "error_code": "",
    }
    defaults.update(over)
    return OpenAPICallLog.objects.create(**defaults)


def test_auditor_sees_every_org_and_empty_username():
    _ensure_group(1)
    _ensure_group(2)
    user_a, _ = create_api_tenant(1, username="alice-org")
    user_b, _ = create_api_tenant(2, username="bob-org")
    _bind_system_user(user_a, 1)
    _bind_system_user(user_b, 2)
    own = _log(username=user_a.username, team_id=1)
    other = _log(username=user_b.username, team_id=2, path="/openapi/v1/cmdb/instances")
    empty = _log(username="", credential_type="", team_id=None, path="/openapi/v1/unknown")

    auditor = BaseUser.objects.create_user(username="auditor", password="pw", domain="domain.com")
    _bind_system_user(auditor, 1)
    client = _client_for(auditor, 1)
    resp = client.get(f"{V}/openapi_call_log/")
    assert resp.status_code == 200
    items = _items(resp)
    ids = {item["id"] for item in items}
    assert own.id in ids
    assert other.id in ids
    assert empty.id in ids
    by_id = {item["id"]: item for item in items}
    assert by_id[own.id]["team_name"] == Group.objects.get(id=1).name
    assert by_id[other.id]["team_name"] == Group.objects.get(id=2).name
    assert by_id[empty.id]["team_name"] is None
    assert "token_id" not in by_id[own.id]
    assert by_id[empty.id]["username"] == ""
    assert by_id[own.id]["error_code"] == ""
    detail = client.get(f"{V}/openapi_call_log/{own.id}/")
    assert detail.status_code == 405


def test_toolbar_filters_hit_username_token_kind_and_outcome():
    _ensure_group(1)
    user_a, _ = create_api_tenant(1, username="filter-user")
    _bind_system_user(user_a, 1)
    _log(username=user_a.username, team_id=1, token_name="other-key")
    target = _log(
        username=user_a.username,
        team_id=1,
        api_kind=OpenAPICallLog.API_KIND_EXTERNAL,
        method="PUT",
        path="/openapi/v1/itsm/tickets/99",
        http_status=403,
        error_code="SCOPE_DENIED",
        credential_type="system_token",
        token_name="itsm-bot",
        system_id="itsm",
    )
    now = timezone.now()
    admin = BaseUser.objects.create_user(username="filteradmin", password="pw", domain="domain.com")
    client = _client_for(admin, 1, is_superuser=True)
    resp = client.get(
        f"{V}/openapi_call_log/",
        {
            "page_size": 20,
            "created_at_start": (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
            "created_at_end": (now + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
            "username": user_a.username,
            "credential_type": "system_token",
            "path": "tickets",
            "api_kind": "external",
            "outcome": "failure",
        },
    )
    assert resp.status_code == 200
    items = _items(resp)
    assert [item["id"] for item in items] == [target.id]

    success = client.get(
        f"{V}/openapi_call_log/",
        {"username": user_a.username, "outcome": "success"},
    )
    assert [item["id"] for item in _items(success)] != [target.id]
    assert target.id not in {item["id"] for item in _items(success)}


def test_export_excel_selected_and_filtered_has_no_payload():
    _ensure_group(1)
    user_a, _ = create_api_tenant(1, username="export-user")
    _bind_system_user(user_a, 1)
    row = _log(username=user_a.username, team_id=1, token_name="export-key", token_id=99)
    admin = BaseUser.objects.create_user(username="exportadmin", password="pw", domain="domain.com")
    client = _client_for(admin, 1, is_superuser=True)
    resp = client.post(f"{V}/openapi_call_log/export_excel/", {"selected_ids": [row.id]}, format="json")
    assert resp.status_code == 200
    assert "spreadsheetml" in resp["Content-Type"]
    workbook = load_workbook(BytesIO(resp.content))
    sheet = workbook.active
    headers = [cell.value for cell in sheet[1]]
    assert headers == [
        "时间",
        "调用账号",
        "组织",
        "源IP",
        "密钥类型",
        "密钥名称",
        "系统ID",
        "接口类型",
        "方法",
        "路径",
        "调用结果",
        "HTTP状态码",
        "错误码",
    ]
    assert "钥匙ID" not in headers
    assert "team_id" not in headers
    assert "服务名" not in headers
    assert "请求正文" not in "".join(str(h) for h in headers)
    assert "响应正文" not in "".join(str(h) for h in headers)
    data_row = [cell.value for cell in sheet[2]]
    assert Group.objects.get(id=1).name in data_row
    assert 1 not in data_row
    assert "成功" in data_row
    assert 99 not in data_row
    body = " ".join(str(cell.value) for row_cells in sheet.iter_rows(min_row=2) for cell in row_cells)
    assert "export-key" in body
    assert user_a.username in body
    assert "未记录" not in body

    filtered = client.post(
        f"{V}/openapi_call_log/export_excel/",
        {"api_kind": "internal", "credential_type": "api_token"},
        format="json",
    )
    assert filtered.status_code == 200
    filtered_book = load_workbook(BytesIO(filtered.content))
    assert filtered_book.active.max_row >= 2


def test_call_result_matrix_and_outcome_buckets():
    _ensure_group(1)
    admin = BaseUser.objects.create_user(username="result-admin", password="pw", domain="domain.com")
    client = _client_for(admin, 1, is_superuser=True)
    internal_ok = _log(username="matrix", path="/internal-ok")
    internal_fail = _log(username="matrix", path="/internal-fail", http_status=500, error_code="INTERNAL_ERROR")
    auth_passed = _log(
        username="matrix",
        path="/ext-ok",
        api_kind=OpenAPICallLog.API_KIND_EXTERNAL,
        http_status=200,
        error_code="",
    )
    auth_denied = _log(
        username="matrix",
        path="/ext-denied",
        api_kind=OpenAPICallLog.API_KIND_EXTERNAL,
        http_status=403,
        error_code="SCOPE_DENIED",
    )
    ext_fail = _log(
        username="matrix",
        path="/ext-timeout",
        api_kind=OpenAPICallLog.API_KIND_EXTERNAL,
        http_status=504,
        error_code="TIMEOUT",
    )
    empty_kind = _log(username="matrix", path="/empty-kind", api_kind="", http_status=200, error_code="")
    unknown_kind = _log(username="matrix", path="/unknown-kind", api_kind="webhook", http_status=200, error_code="")
    not_found = _log(
        username="matrix",
        path="/ext-404",
        api_kind=OpenAPICallLog.API_KIND_EXTERNAL,
        http_status=404,
        error_code="NOT_FOUND",
    )

    resp = client.get(f"{V}/openapi_call_log/", {"username": "matrix", "page_size": 50})
    assert resp.status_code == 200
    by_id = {item["id"]: item for item in _items(resp)}
    assert by_id[internal_ok.id]["call_result"] == "success"
    assert by_id[internal_fail.id]["call_result"] == "failure"
    assert by_id[auth_passed.id]["call_result"] == "auth_passed"
    assert by_id[auth_denied.id]["call_result"] == "auth_denied"
    assert by_id[ext_fail.id]["call_result"] == "failure"
    assert by_id[empty_kind.id]["call_result"] == "failure"
    assert by_id[unknown_kind.id]["call_result"] == "failure"
    assert by_id[not_found.id]["call_result"] == "failure"
    assert by_id[auth_passed.id]["error_code"] == ""
    assert by_id[internal_ok.id]["error_code"] == ""

    success_ids = {item["id"] for item in _items(client.get(f"{V}/openapi_call_log/", {"username": "matrix", "outcome": "success"}))}
    failure_ids = {item["id"] for item in _items(client.get(f"{V}/openapi_call_log/", {"username": "matrix", "outcome": "failure"}))}
    assert success_ids == {internal_ok.id, auth_passed.id}
    assert {auth_denied.id, ext_fail.id, empty_kind.id, unknown_kind.id, not_found.id, internal_fail.id}.issubset(failure_ids)
    assert internal_ok.id not in failure_ids
    assert auth_passed.id not in failure_ids


def test_new_filters_and_combined_toolbar():
    _ensure_group(1)
    admin = BaseUser.objects.create_user(username="newfilter-admin", password="pw", domain="domain.com")
    client = _client_for(admin, 1, is_superuser=True)
    target = _log(
        username="combo",
        token_name="alpha-secret",
        source_ip="10.9.8.7",
        http_status=201,
        path="/openapi/v1/itsm/tickets",
        credential_type="api_token",
        api_kind=OpenAPICallLog.API_KIND_INTERNAL,
    )
    _log(
        username="combo",
        token_name="beta-secret",
        source_ip="10.1.1.1",
        http_status=200,
        path="/openapi/v1/itsm/tickets",
    )
    by_token = client.get(f"{V}/openapi_call_log/", {"token_name": "alpha"})
    assert [item["id"] for item in _items(by_token)] == [target.id]
    by_ip = client.get(f"{V}/openapi_call_log/", {"source_ip": "10.9.8"})
    assert [item["id"] for item in _items(by_ip)] == [target.id]
    by_status = client.get(f"{V}/openapi_call_log/", {"http_status": 201})
    assert [item["id"] for item in _items(by_status)] == [target.id]

    combined = client.get(
        f"{V}/openapi_call_log/",
        {
            "username": "combo",
            "path": "tickets",
            "credential_type": "api_token",
            "api_kind": "internal",
            "token_name": "alpha",
            "source_ip": "10.9.8",
            "http_status": 201,
            "outcome": "success",
        },
    )
    assert [item["id"] for item in _items(combined)] == [target.id]


def test_export_over_limit_returns_400(monkeypatch):
    from apps.system_mgmt.utils import audit_log_export

    _ensure_group(1)
    admin = BaseUser.objects.create_user(username="cap-admin", password="pw", domain="domain.com")
    client = _client_for(admin, 1, is_superuser=True)
    _log(username="cap-one", path="/one")
    _log(username="cap-two", path="/two")
    monkeypatch.setattr(audit_log_export, "EXPORT_MAX_ROWS", 1)
    resp = client.post(f"{V}/openapi_call_log/export_excel/", {}, format="json")
    assert resp.status_code == 400
    assert "spreadsheetml" not in (resp.get("Content-Type") or "")


def test_export_empty_username_and_error_code_are_blank():
    _ensure_group(1)
    admin = BaseUser.objects.create_user(username="blank-admin", password="pw", domain="domain.com")
    client = _client_for(admin, 1, is_superuser=True)
    row = _log(username="", path="/blank", error_code="", credential_type="", token_name="")
    resp = client.post(f"{V}/openapi_call_log/export_excel/", {"selected_ids": [row.id]}, format="json")
    assert resp.status_code == 200
    workbook = load_workbook(BytesIO(resp.content))
    data_row = [cell.value for cell in workbook.active[2]]
    assert data_row[1] in ("", None)
    assert data_row[-1] in ("", None)
    assert "未记录" not in [str(v) for v in data_row if v is not None]


def test_system_id_is_required_only_for_system_token():
    _log(credential_type="system_token", system_id="itsm", token_name="itsm-key")
    _log(credential_type="api_token", system_id="", token_name="personal")
    _log(credential_type="", system_id="", username="", token_name="")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _log(credential_type="system_token", system_id="")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _log(credential_type="api_token", system_id="itsm")
