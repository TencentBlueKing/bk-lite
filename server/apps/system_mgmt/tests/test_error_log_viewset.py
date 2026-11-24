from io import BytesIO

import pytest
from openpyxl import load_workbook
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from apps.system_mgmt.models import ErrorLog, Group, User
from apps.system_mgmt.utils import audit_log_export
from apps.system_mgmt.utils.group_filter_mixin import GroupFilterMixin
from apps.system_mgmt.viewset.error_log_viewset import ErrorLogViewSet

pytestmark = pytest.mark.django_db

VISIBLE_DOMAIN = "domain.com"
PARSED_MESSAGE = "[GET] /api/v1/monitor/alert_rule/\n错误类型: ValueError\n错误信息: node_id 必填"
JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.abc"


@pytest.fixture(autouse=True)
def scope_queryset_like_current_team(monkeypatch):
    def _visible(self):
        return self.queryset.filter(domain=VISIBLE_DOMAIN)

    monkeypatch.setattr(GroupFilterMixin, "get_queryset", _visible)


def _admin():
    from apps.base.models import User as BaseUser

    admin = BaseUser.objects.create_user(
        username="error-log-admin",
        password="pw",
        domain=VISIBLE_DOMAIN,
        locale="zh-Hans",
        email="error-log-admin@x.com",
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


def _list_items(client, params=None):
    query = {"page": 1, "page_size": 50}
    if params:
        query.update(params)
    resp = client.get("/api/v1/system_mgmt/error_log/", query)
    assert resp.status_code == 200
    payload = resp.json()
    if isinstance(payload, list):
        return payload
    return payload.get("items") or payload.get("data", {}).get("items") or []


def _log(**over):
    defaults = {
        "username": "alice",
        "app": "monitor",
        "module": "alert_rule",
        "error_message": PARSED_MESSAGE,
        "stack_trace": 'File "views.py", line 1\n',
        "domain": VISIBLE_DOMAIN,
    }
    defaults.update(over)
    return ErrorLog.objects.create(**defaults)


def _export(admin, team_id, body):
    request = APIRequestFactory().post("/export_excel/", body, format="json")
    request.COOKIES["current_team"] = str(team_id)
    force_authenticate(request, user=admin)
    return ErrorLogViewSet.as_view({"post": "export_excel"})(request)


def test_list_parsed_template_and_masked_fields():
    admin = _admin()
    team_id = _team_user("alice")
    client = _client(admin, team_id)
    _log(
        error_message="[GET] /api/v1/monitor/alert_rule/\n错误类型: ValueError\n错误信息: node_id 必填",
    )
    _log(
        username="bob",
        error_message="GET /x/?token=abc password=hunter2 Invalid or expired token",
        stack_trace="",
        app="monitor",
        module="other",
    )
    items = _list_items(client)
    parsed = next(item for item in items if item["parsed"])
    assert parsed["reason"] == "node_id 必填"
    assert parsed["exception_type"] == "ValueError"
    assert parsed["method"] == "GET"
    assert parsed["path"] == "/api/v1/monitor/alert_rule/"
    assert "?" not in parsed["path"]
    unparsed = next(item for item in items if not item["parsed"])
    assert unparsed["recorded_text"]
    assert "token=****" in unparsed["recorded_text"]
    assert "password=****" in unparsed["recorded_text"]
    assert "Invalid or expired token" in unparsed["recorded_text"]
    assert "hunter2" not in unparsed["recorded_text"]
    assert "hunter2" not in unparsed["error_message"]
    assert "abc" not in unparsed["error_message"]
    assert unparsed["method"] == ""
    assert unparsed["reason"] == ""


def test_list_json_does_not_run_jwt_regex():
    admin = _admin()
    team_id = _team_user("alice")
    client = _client(admin, team_id)
    _log(error_message=f"boom {JWT}", stack_trace=f"trace {JWT}")
    item = _list_items(client)[0]
    assert JWT in item["recorded_text"]
    assert JWT in item["stack_text"]
    assert JWT in item["stack_trace"]


def test_keyword_and_system_manager_filter_hits_system_mgmt_row():
    admin = _admin()
    team_id = _team_user("alice")
    client = _client(admin, team_id)
    _log(app="system_mgmt", module="user", error_message="node_id 必填 in system")
    _log(app="monitor", error_message="node_id 必填 in monitor")
    _log(app="system_mgmt", error_message="unrelated")
    items = _list_items(client, {"keyword": "node_id", "app": "system-manager"})
    assert len(items) == 1
    assert items[0]["app"] == "system_mgmt"
    assert "node_id" in items[0]["error_message"]


def test_retrieve_stays_405():
    admin = _admin()
    team_id = _team_user("alice")
    client = _client(admin, team_id)
    row = _log()
    resp = client.get(f"/api/v1/system_mgmt/error_log/{row.id}/")
    assert resp.status_code == 405


def test_export_over_limit_returns_400(monkeypatch):
    admin = _admin()
    team_id = _team_user("alice")
    _log(error_message="one")
    _log(error_message="two")
    monkeypatch.setattr(audit_log_export, "EXPORT_MAX_ROWS", 1)
    response = _export(admin, team_id, {})
    assert response.status_code == 400
    assert response.get("Content-Disposition") is None


def test_export_masks_jwt_and_unparsed_cells():
    admin = _admin()
    team_id = _team_user("alice")
    parsed = _log()
    _log(
        username="bob",
        error_message=f"free text {JWT}",
        stack_trace="",
        app="monitor",
        module="other",
    )
    response = _export(admin, team_id, {"selected_ids": [parsed.id]})
    assert response.status_code == 200
    sheet = load_workbook(BytesIO(response.content)).active
    headers = [sheet.cell(row=1, column=index).value for index in range(1, 11)]
    assert headers == [
        "时间",
        "关联用户",
        "业务模块",
        "错误原因",
        "异常类型",
        "请求方法",
        "路径",
        "技术模块",
        "已记录错误文本",
        "堆栈",
    ]
    parsed_row = [sheet.cell(row=2, column=index).value for index in range(1, 11)]
    assert parsed_row[3] == "node_id 必填"
    assert parsed_row[4] == "ValueError"
    assert parsed_row[5] == "GET"
    assert parsed_row[6] == "/api/v1/monitor/alert_rule/"
    assert "File" in parsed_row[9]

    response = _export(admin, team_id, {})
    sheet = load_workbook(BytesIO(response.content)).active
    rows = [[sheet.cell(row=r, column=c).value for c in range(1, 11)] for r in range(2, sheet.max_row + 1)]
    unparsed = next(row for row in rows if row[1] == "bob")
    assert unparsed[3] == "未记录"
    assert unparsed[4] == "未记录"
    assert unparsed[5] == "未记录"
    assert unparsed[6] == "未记录"
    assert unparsed[9] == "未记录堆栈"
    assert JWT not in unparsed[8]
    assert "****" in unparsed[8]
