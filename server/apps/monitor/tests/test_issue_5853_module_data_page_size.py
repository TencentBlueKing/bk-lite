"""Issue #5853：监控数据规则分页必须拒绝非法 page/page_size，且 page_size 上限 100。"""

import json
import types

import pytest
from django.db.models.query import QuerySet
from rest_framework.test import APIRequestFactory, force_authenticate

import apps.cmdb.models  # noqa: F401  INSTALL_APPS 需含 cmdb（monitor.nats.monitor 导入 cmdb.services）
import apps.node_mgmt.models  # noqa: F401  INSTALL_APPS 需含 node_mgmt（monitor.apps.ready → nats.monitor）
from apps.monitor.models.monitor_object import MonitorInstance, MonitorInstanceOrganization, MonitorObject
from apps.monitor.nats import permission as nats_perm
from apps.system_mgmt.viewset.group_data_rule_viewset import GroupDataRuleViewSet

pytestmark = pytest.mark.django_db


def _request_user(group_ids):
    return types.SimpleNamespace(
        username="issue-5853-operator",
        domain="domain.com",
        locale="en",
        is_authenticated=True,
        is_superuser=False,
        permission={"system-manager": {"data_permission-View"}},
        group_list=[{"id": group_id} for group_id in group_ids],
    )


def _json_payload(response):
    return json.loads(response.content)


def _seed_instances():
    obj = MonitorObject.objects.create(name="Issue5853Obj", level="base")
    visible = []
    for idx in range(3):
        inst = MonitorInstance.objects.create(id=f"issue-5853-org7-{idx}", name=f"org7-{idx}", monitor_object=obj)
        MonitorInstanceOrganization.objects.create(monitor_instance=inst, organization=7)
        visible.append(inst)
    hidden = MonitorInstance.objects.create(id="issue-5853-org8", name="org8-hidden", monitor_object=obj)
    MonitorInstanceOrganization.objects.create(monitor_instance=hidden, organization=8)
    return obj, visible, hidden


def test_legal_page_size_10_returns_one_org_page():
    obj, visible, hidden = _seed_instances()

    out = nats_perm.get_monitor_module_data("instance", obj.id, 1, 10, 7)

    assert out.get("result", True) is True
    assert out["count"] == 3
    assert {item["id"] for item in out["items"]} == {inst.id for inst in visible}
    assert hidden.id not in {item["id"] for item in out["items"]}


def test_legal_page_size_100_still_works():
    obj, visible, _hidden = _seed_instances()

    out = nats_perm.get_monitor_module_data("instance", obj.id, 1, 100, 7)

    assert out.get("result", True) is True
    assert out["count"] == 3
    assert len(out["items"]) == 3
    assert {item["id"] for item in out["items"]} == {inst.id for inst in visible}


@pytest.mark.parametrize("page,page_size", [(1, 101), (1, 1000000), (0, 10), (1, -1), (1, 0), ("x", 10), (1, "1e2")])
def test_handler_rejects_illegal_page_without_listing(page, page_size, monkeypatch):
    obj, _visible, _hidden = _seed_instances()
    sliced = {}
    original_getitem = QuerySet.__getitem__

    def tracking_getitem(self, key):
        sliced["key"] = key
        return original_getitem(self, key)

    monkeypatch.setattr(QuerySet, "__getitem__", tracking_getitem)

    out = nats_perm.get_monitor_module_data("instance", obj.id, page, page_size, 7)

    assert out.get("result") is False
    assert out.get("message")
    assert "key" not in sliced


def test_get_app_data_rejects_non_integer_page_with_400(monkeypatch):
    captured = {}

    class FakeClient:
        def get_module_data(self, **kwargs):
            captured.update(kwargs)
            return {"count": 0, "items": []}

    def fake_get_client(params):
        params.pop("app")
        return FakeClient()

    monkeypatch.setattr(GroupDataRuleViewSet, "get_client", staticmethod(fake_get_client))

    request = APIRequestFactory().get(
        "/system_mgmt/api/group_data_rule/get_app_data/",
        {
            "app": "monitor",
            "module": "instance",
            "child_module": "host",
            "page": "abc",
            "page_size": "10",
            "group_id": "7",
        },
    )
    force_authenticate(request, user=_request_user([7]))

    response = GroupDataRuleViewSet.as_view({"get": "get_app_data"})(request)
    payload = _json_payload(response)

    assert response.status_code == 400
    assert payload["result"] is False
    assert payload.get("message")
    assert captured == {}


@pytest.mark.parametrize("page,page_size", [("0", "10"), ("1", "-1")])
def test_get_app_data_rejects_non_positive_page_with_400(page, page_size, monkeypatch):
    captured = {}

    class FakeClient:
        def get_module_data(self, **kwargs):
            captured.update(kwargs)
            return {"count": 0, "items": []}

    def fake_get_client(params):
        params.pop("app")
        return FakeClient()

    monkeypatch.setattr(GroupDataRuleViewSet, "get_client", staticmethod(fake_get_client))

    request = APIRequestFactory().get(
        "/system_mgmt/api/group_data_rule/get_app_data/",
        {
            "app": "monitor",
            "module": "instance",
            "child_module": "host",
            "page": page,
            "page_size": page_size,
            "group_id": "7",
        },
    )
    force_authenticate(request, user=_request_user([7]))

    response = GroupDataRuleViewSet.as_view({"get": "get_app_data"})(request)
    payload = _json_payload(response)

    assert response.status_code == 400
    assert payload["result"] is False
    assert payload.get("message")
    assert captured == {}


def test_get_app_data_keeps_default_page_and_page_size(monkeypatch):
    captured = {}

    class FakeClient:
        def get_module_data(self, **kwargs):
            captured.update(kwargs)
            return {"count": 0, "items": []}

    def fake_get_client(params):
        params.pop("app")
        return FakeClient()

    monkeypatch.setattr(GroupDataRuleViewSet, "get_client", staticmethod(fake_get_client))

    request = APIRequestFactory().get(
        "/system_mgmt/api/group_data_rule/get_app_data/",
        {
            "app": "monitor",
            "module": "instance",
            "child_module": "host",
            "group_id": "7",
        },
    )
    force_authenticate(request, user=_request_user([7]))

    response = GroupDataRuleViewSet.as_view({"get": "get_app_data"})(request)
    payload = _json_payload(response)

    assert response.status_code == 200
    assert payload == {"result": True, "data": {"count": 0, "items": []}}
    assert captured["page"] == 1
    assert captured["page_size"] == 10


def test_get_app_data_does_not_cap_non_monitor_page_size(monkeypatch):
    captured = {}

    class FakeClient:
        def get_module_data(self, **kwargs):
            captured.update(kwargs)
            return {"count": 0, "items": []}

    def fake_get_client(params):
        params.pop("app")
        return FakeClient()

    monkeypatch.setattr(GroupDataRuleViewSet, "get_client", staticmethod(fake_get_client))

    request = APIRequestFactory().get(
        "/system_mgmt/api/group_data_rule/get_app_data/",
        {
            "app": "job",
            "module": "script",
            "child_module": "host",
            "page": "1",
            "page_size": "1000000",
            "group_id": "7",
        },
    )
    force_authenticate(request, user=_request_user([7]))

    response = GroupDataRuleViewSet.as_view({"get": "get_app_data"})(request)
    payload = _json_payload(response)

    assert response.status_code == 200
    assert payload["result"] is True
    assert captured["page_size"] == 1000000
