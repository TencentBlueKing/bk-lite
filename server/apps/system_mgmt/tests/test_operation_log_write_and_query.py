import json
import logging
import types
from io import BytesIO

import pytest
from openpyxl import load_workbook
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from apps.system_mgmt.models import App, Group, OperationLog, User
from apps.system_mgmt.utils.group_filter_mixin import GroupFilterMixin
from apps.system_mgmt.utils.operation_log_utils import OPERATION_LOG_WRITE_FAILED, SENSITIVE_VALUE_PLACEHOLDER, log_operation
from apps.system_mgmt.viewset.operation_log_viewset import OperationLogViewSet

pytestmark = pytest.mark.django_db

SENTINEL = "op-log-secret-password-sentinel-9f3a"
VISIBLE_DOMAIN = "domain.com"


@pytest.fixture(autouse=True)
def scope_queryset_like_current_team(monkeypatch):
    def _visible(self):
        return self.queryset.filter(domain=VISIBLE_DOMAIN)

    monkeypatch.setattr(GroupFilterMixin, "get_queryset", _visible)


def _request(username="op-user"):
    return types.SimpleNamespace(
        user=types.SimpleNamespace(username=username, domain=VISIBLE_DOMAIN),
        META={"REMOTE_ADDR": "10.0.0.5"},
    )


def _admin():
    from apps.base.models import User as BaseUser

    admin = BaseUser.objects.create_user(
        username="oplog-query-admin",
        password="pw",
        domain=VISIBLE_DOMAIN,
        locale="zh-Hans",
        email="oplog-query-admin@x.com",
    )
    admin.is_superuser = True
    admin.save()
    return admin


def _team_user(username):
    group, _created = Group.objects.get_or_create(name="Default", parent_id=0)
    User.objects.create(
        username=username,
        password="x",
        display_name=username,
        email=f"{username}@x.com",
        domain=VISIBLE_DOMAIN,
        group_list=[group.id],
    )
    return group.id


def _client(admin, team_id):
    client = APIClient()
    client.force_authenticate(user=admin)
    client.cookies["current_team"] = str(team_id)
    return client


def _list_payload(client, params=None):
    query = {"page": 1, "page_size": 50}
    if params:
        query.update(params)
    resp = client.get("/api/v1/system_mgmt/operation_log/", query)
    assert resp.status_code == 200
    payload = resp.json()
    if isinstance(payload, list):
        return payload
    return payload.get("items") or payload.get("data", {}).get("items") or []


def _list_items(client):
    return _list_payload(client)


def test_log_operation_without_outcome_stores_empty_string():
    log = log_operation(_request(), "create", "system-manager", "测试操作")
    log.refresh_from_db()
    assert log.outcome == ""
    assert log.target_name == ""
    assert log.failure_reason == ""


def test_log_operation_redacts_sensitive_detail_before_persist():
    payload = {
        "Password": SENTINEL,
        "nested": {"api_token": SENTINEL, "otp_code": SENTINEL, "keep": "visible"},
        "list": [{"private_key": SENTINEL, "name": "ok"}],
        "access_key": SENTINEL,
        "client_secret": SENTINEL,
    }
    log = log_operation(_request(), "update", "system-manager", "改密", detail=payload, outcome="success")
    log.refresh_from_db()
    raw = json.dumps(log.detail)
    assert SENTINEL not in raw
    assert log.detail["Password"] == SENSITIVE_VALUE_PLACEHOLDER
    assert log.detail["nested"]["api_token"] == SENSITIVE_VALUE_PLACEHOLDER
    assert log.detail["nested"]["otp_code"] == SENSITIVE_VALUE_PLACEHOLDER
    assert log.detail["nested"]["keep"] == "visible"
    assert log.detail["list"][0]["private_key"] == SENSITIVE_VALUE_PLACEHOLDER
    assert log.detail["access_key"] == SENSITIVE_VALUE_PLACEHOLDER
    assert log.detail["client_secret"] == SENSITIVE_VALUE_PLACEHOLDER
    assert payload["Password"] == SENTINEL


def test_log_operation_write_failure_logs_template_without_payload(monkeypatch, caplog):
    def _boom(*args, **kwargs):
        raise RuntimeError("persist-failed")

    monkeypatch.setattr(OperationLog.objects, "create", _boom)
    with caplog.at_level(logging.ERROR, logger="system-manager"):
        result = log_operation(
            _request(),
            "create",
            "system-manager",
            "测试操作",
            detail={"password": SENTINEL},
            outcome="success",
        )
    assert result is None
    assert OperationLog.objects.count() == 0
    records = [item for item in caplog.records if item.msg == OPERATION_LOG_WRITE_FAILED]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.ERROR
    assert record.args == ("RuntimeError",)
    assert record.exc_info is not None
    rendered = record.getMessage()
    formatted = logging.Formatter("%(levelname)s %(message)s").format(record)
    assert rendered == "event=operation_log_write_failed failed_stage=persist error_type=RuntimeError"
    blob = rendered + formatted + caplog.text
    assert SENTINEL not in blob
    assert not any(item.levelno >= logging.ERROR and item is not record for item in caplog.records)


def test_list_does_not_present_empty_outcome_as_success():
    admin = _admin()
    team_id = _team_user("alice")
    app, _created = App.objects.get_or_create(name="cmdb", defaults={"display_name": "配置管理", "url": "/cmdb"})
    if app.display_name != "配置管理":
        app.display_name = "配置管理"
        app.save(update_fields=["display_name"])
    OperationLog.objects.create(
        username="alice",
        domain=VISIBLE_DOMAIN,
        source_ip="127.0.0.1",
        app="cmdb",
        action_type="create",
        summary="未标注结果",
        outcome="",
    )
    items = _list_items(_client(admin, team_id))
    assert items
    row = next(item for item in items if item["summary"] == "未标注结果")
    assert row["outcome"] == ""
    assert row["app_name"] == "CMDB"
    assert "成功" not in json.dumps(row, ensure_ascii=False)
    assert row.get("action_type_display") != "成功"


def test_list_uses_bilingual_app_name_not_display_name():
    admin = _admin()
    team_id = _team_user("alice")
    App.objects.update_or_create(
        name="system-manager",
        defaults={"display_name": "Setting", "url": "/system-manager", "is_build_in": True},
    )
    App.objects.update_or_create(
        name="acme-ops",
        defaults={"display_name": "Acme Ops", "url": "/acme", "is_build_in": False},
    )
    OperationLog.objects.create(
        username="alice",
        domain=VISIBLE_DOMAIN,
        source_ip="127.0.0.1",
        app="system-manager",
        action_type="update",
        summary="setting-row",
        outcome="success",
    )
    OperationLog.objects.create(
        username="alice",
        domain=VISIBLE_DOMAIN,
        source_ip="127.0.0.1",
        app="acme-ops",
        action_type="update",
        summary="custom-row",
        outcome="success",
    )
    items = _list_items(_client(admin, team_id))
    setting_row = next(item for item in items if item["summary"] == "setting-row")
    custom_row = next(item for item in items if item["summary"] == "custom-row")
    assert setting_row["app_name"] == "系统管理"
    assert setting_row["app_name"] != "Setting"
    assert custom_row["app_name"] == "Acme Ops"

    admin.locale = "en"
    admin.save(update_fields=["locale"])
    en_items = _list_items(_client(admin, team_id))
    en_row = next(item for item in en_items if item["summary"] == "setting-row")
    assert en_row["app_name"] == "System Management"


def test_list_redacts_legacy_plaintext_detail():
    admin = _admin()
    team_id = _team_user("alice")
    OperationLog.objects.create(
        username="alice",
        domain=VISIBLE_DOMAIN,
        source_ip="127.0.0.1",
        app="cmdb",
        action_type="update",
        summary="旧明文",
        detail={"password": SENTINEL, "token": SENTINEL, "name": "keep"},
        outcome="success",
    )
    stored = OperationLog.objects.get(summary="旧明文")
    assert stored.detail["password"] == SENTINEL
    items = _list_items(_client(admin, team_id))
    row = next(item for item in items if item["summary"] == "旧明文")
    dumped = json.dumps(row, ensure_ascii=False)
    assert SENTINEL not in dumped
    assert row["detail"]["password"] == SENSITIVE_VALUE_PLACEHOLDER
    assert row["detail"]["token"] == SENSITIVE_VALUE_PLACEHOLDER
    assert row["detail"]["name"] == "keep"


def test_target_filter_matches_name_or_id_with_action_type():
    admin = _admin()
    team_id = _team_user("alice")
    client = _client(admin, team_id)
    OperationLog.objects.create(
        username="alice",
        domain=VISIBLE_DOMAIN,
        source_ip="127.0.0.1",
        app="cmdb",
        action_type="update",
        summary="name-hit",
        target_name="web-host",
        target_id="111",
    )
    OperationLog.objects.create(
        username="alice",
        domain=VISIBLE_DOMAIN,
        source_ip="127.0.0.1",
        app="cmdb",
        action_type="delete",
        summary="id-hit-wrong-type",
        target_name="other",
        target_id="web-host",
    )
    OperationLog.objects.create(
        username="alice",
        domain=VISIBLE_DOMAIN,
        source_ip="127.0.0.1",
        app="cmdb",
        action_type="update",
        summary="id-hit",
        target_name="db-host",
        target_id="web-99",
    )
    OperationLog.objects.create(
        username="alice",
        domain=VISIBLE_DOMAIN,
        source_ip="127.0.0.1",
        app="cmdb",
        action_type="update",
        summary="miss",
        target_name="leaf",
        target_id="000",
    )
    items = _list_payload(client, {"target": "web", "action_type": "update"})
    summaries = {item["summary"] for item in items}
    assert summaries == {"name-hit", "id-hit"}


def test_outcome_filter_covers_four_values():
    admin = _admin()
    team_id = _team_user("alice")
    client = _client(admin, team_id)
    for outcome, summary in (
        ("success", "ok-row"),
        ("failure", "fail-row"),
        ("accepted", "accepted-row"),
        ("", "blank-row"),
    ):
        OperationLog.objects.create(
            username="alice",
            domain=VISIBLE_DOMAIN,
            source_ip="127.0.0.1",
            app="cmdb",
            action_type="execute",
            summary=summary,
            outcome=outcome,
        )
    mapping = {
        "success": "ok-row",
        "failure": "fail-row",
        "accepted": "accepted-row",
        "unrecorded": "blank-row",
    }
    for query, summary in mapping.items():
        items = _list_payload(client, {"outcome": query})
        assert {item["summary"] for item in items} == {summary}


def _export_sheet(admin, team_id, body):
    request = APIRequestFactory().post("/export_excel/", body, format="json")
    request.COOKIES["current_team"] = str(team_id)
    force_authenticate(request, user=admin)
    response = OperationLogViewSet.as_view({"post": "export_excel"})(request)
    assert response.status_code == 200
    return load_workbook(BytesIO(response.content)).active


def test_export_columns_app_display_name_and_redaction():
    admin = _admin()
    team_id = _team_user("alice")
    app, _created = App.objects.get_or_create(name="cmdb", defaults={"display_name": "配置管理", "url": "/cmdb"})
    if app.display_name != "配置管理":
        app.display_name = "配置管理"
        app.save(update_fields=["display_name"])
    OperationLog.objects.create(
        username="alice",
        domain=VISIBLE_DOMAIN,
        source_ip="127.0.0.1",
        app="cmdb",
        action_type="update",
        summary="export-row",
        target_type="host",
        target_name="web-1",
        target_id="42",
        outcome="failure",
        failure_reason="校验失败",
        detail={"password": SENTINEL},
    )
    sheet = _export_sheet(admin, team_id, {})
    headers = [sheet.cell(row=1, column=index).value for index in range(1, 13)]
    assert headers == [
        "用户名",
        "域名",
        "操作时间",
        "源IP地址",
        "应用",
        "操作类型",
        "概要描述",
        "对象类型",
        "对象名称",
        "对象ID",
        "执行结果",
        "失败原因",
    ]
    values = [sheet.cell(row=2, column=index).value for index in range(1, 13)]
    assert values[4] == "CMDB"
    assert values[7] == "host"
    assert values[8] == "web-1"
    assert values[9] == "42"
    assert values[10] == "失败"
    assert values[11] == "校验失败"
    dumped = " ".join("" if cell is None else str(cell) for cell in values)
    assert SENTINEL not in dumped
    assert "成功" != values[10]


def test_export_blank_failure_reason_only_when_outcome_is_failure():
    admin = _admin()
    team_id = _team_user("alice")
    OperationLog.objects.create(
        username="alice",
        domain=VISIBLE_DOMAIN,
        source_ip="127.0.0.1",
        app="cmdb",
        action_type="update",
        summary="failed-without-reason",
        outcome="failure",
        failure_reason="",
    )
    OperationLog.objects.create(
        username="alice",
        domain=VISIBLE_DOMAIN,
        source_ip="127.0.0.1",
        app="cmdb",
        action_type="update",
        summary="succeeded-without-reason",
        outcome="success",
        failure_reason="",
    )
    sheet = _export_sheet(admin, team_id, {})
    reasons = {sheet.cell(row=row, column=7).value: sheet.cell(row=row, column=12).value for row in range(2, sheet.max_row + 1)}
    assert reasons["failed-without-reason"] == "未记录"
    assert reasons["succeeded-without-reason"] == "-"
