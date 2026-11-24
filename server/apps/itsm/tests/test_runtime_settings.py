import json

import pytest

from apps.itsm.models import HandlerGroup, ItsmSetting
from apps.itsm.tests.test_review_regressions import request
from apps.itsm.views.api import HandlerGroupView, basic_settings
from apps.itsm.views.attachments import presign_attachment
from apps.system_mgmt.models import User

pytestmark = pytest.mark.django_db


def settings_data(response):
    assert response.status_code == 200, response.content
    return json.loads(response.content)["data"]


def test_settings_runtime_is_read_only_tenant_projection():
    saved = settings_data(basic_settings(request("post", {"product_name": "  研发服务台  ", "show_process_log": False}, permissions=["setting-Edit"])))
    assert saved["product_name"] == "研发服务台"
    assert settings_data(basic_settings(request(permissions=["setting-View"])))["can_edit"] is False
    runtime = settings_data(basic_settings(request(payload={"runtime": "1"}, permissions=["portal-View"])))
    assert runtime["product_name"] == "研发服务台"
    assert runtime["show_process_log"] is False
    assert "can_edit" not in runtime
    assert basic_settings(request(permissions=["portal-View"])).status_code == 403
    other = settings_data(basic_settings(request(payload={"runtime": "1"}, permissions=["ticket-View"], domain="other.example")))
    assert other["product_name"] == "ITSM"
    assert not ItsmSetting.objects.filter(domain="other.example", key="basic").exists()


@pytest.mark.parametrize("payload", [{"tab_title": " "}, {"show_process_log": "false"}, {"user_display": "email"}, {"attachment_types": ".*"}])
def test_invalid_settings_cannot_be_saved(payload):
    response = basic_settings(request("post", payload, permissions=["setting-Edit"]))
    assert response.status_code == 400
    assert not ItsmSetting.objects.filter(key="basic").exists()


def test_attachment_policy_enforced_before_signed_upload(monkeypatch):
    monkeypatch.setattr("apps.itsm.views.attachments.presign_upload", lambda name: {"object_name": name})
    editor = request("post", {"attachment_types": ".PDF, pdf"}, permissions=["setting-Edit"])
    assert settings_data(basic_settings(editor))["attachment_types"] == "pdf"
    permissions = ["ticket-View", "ticket-Add"]
    assert presign_attachment(request("post", {"filename": "申请.PDF"}, permissions=permissions)).status_code == 200
    assert presign_attachment(request("post", {"filename": "申请.png"}, permissions=permissions)).status_code == 400
    other = request("post", {"filename": "压缩包.zip"}, permissions=permissions, domain="other.example")
    assert presign_attachment(other).status_code == 200


def handler_group_request(method, payload=None, permissions=None):
    req = request(method, payload, permissions=permissions or ["org-Edit", "org-View"])
    req.data = payload or {}
    return getattr(HandlerGroupView(), method)(req)


def test_handler_group_preserves_explicit_leaders_on_partial_edit():
    group = HandlerGroup.objects.create(name="网络组", members=["one", "two"], leaders=["two"])
    assert handler_group_request("post", {"id": group.id, "name": "运维组"}).status_code == 200
    group.refresh_from_db()
    assert group.leaders == ["two"]
    assert handler_group_request("post", {"id": group.id, "leaders": []}).status_code == 200
    group.refresh_from_db()
    assert group.leaders == []


def test_handler_group_respects_permissions_and_domain_membership():
    User.objects.create(username="local", display_name="本域成员", domain="domain.com")
    User.objects.create(username="remote", display_name="其他组织成员", domain="other.example")
    assert handler_group_request("get", permissions=["org-View"]).data["can_edit"] is False
    assert handler_group_request("post", {"name": "运维组", "members": ["local"], "leaders": ["remote"]}).status_code == 400
    assert handler_group_request("post", {"name": "运维组", "members": ["local", "remote"], "leaders": ["local"]}).status_code == 400
    response = handler_group_request("post", {"name": "运维组", "members": ["local"], "leaders": ["local"]})
    assert response.status_code == 200
    assert HandlerGroup.objects.get(id=response.data["id"]).leaders == ["local"]
