"""monitor 视图层补充测试（通过 DRF api_client 走真实路由 + 序列化器）。

外部边界（NodeMgmt RPC / get_permission_rules / InstanceConfigService）mock。
"""

import pytest

from apps.monitor.models.monitor_condition import (
    MonitorCondition,
    MonitorConditionOrganization,
)
from apps.monitor.models.monitor_metrics import Metric, MetricGroup
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.plugin import MonitorPlugin

pytestmark = pytest.mark.django_db

BASE = "/api/v1/monitor"


def _patch_current_team_scope(mocker, *, teams=(1,), assignable=(1,)):
    mocker.patch(
        "apps.core.utils.current_team_scope.SystemMgmt.get_authorized_groups_scoped",
        return_value={"result": True, "data": list(teams)},
    )
    mocker.patch(
        "apps.core.utils.current_team_scope.SystemMgmt.get_assignable_groups",
        return_value={"result": True, "data": list(assignable)},
    )


class TestUnitView:
    def test_list_units(self, api_client):
        resp = api_client.get(f"{BASE}/api/unit/list/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        ids = {u["unit_id"] for u in data}
        assert "bytes" in ids and "percent" in ids

    def test_list_by_system_specific(self, api_client):
        resp = api_client.get(f"{BASE}/api/unit/by_system/?system=data_bytes")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert all(u["system"] == "data_bytes" for u in data)
        assert {u["unit_id"] for u in data} >= {"bytes", "kibibytes"}

    def test_list_by_system_grouped(self, api_client):
        resp = api_client.get(f"{BASE}/api/unit/by_system/")
        assert resp.status_code == 200
        data = resp.json()["data"]
        systems = {row["system_name"] for row in data}
        assert "data_bytes" in systems
        for row in data:
            assert "system_description" in row and "units" in row


class TestMetricGroupView:
    def _setup(self):
        obj = MonitorObject.objects.create(name="MGViewObj", level="base")
        plugin = MonitorPlugin.objects.create(name="MGViewPlugin")
        g1 = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g1", sort_order=2)
        g2 = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g2", sort_order=1)
        return obj, g1, g2

    def test_list_returns_groups(self, api_client):
        obj, g1, g2 = self._setup()
        resp = api_client.get(f"{BASE}/api/metrics_group/?monitor_object_id={obj.id}")
        assert resp.status_code == 200
        names = {item["name"] for item in resp.json()["data"]}
        assert {"g1", "g2"} <= names

    def test_set_order(self, api_client):
        obj, g1, g2 = self._setup()
        payload = [{"id": g1.id, "sort_order": 9}, {"id": g2.id, "sort_order": 8}]
        resp = api_client.post(f"{BASE}/api/metrics_group/set_order/", payload, format="json")
        assert resp.status_code == 200
        g1.refresh_from_db()
        assert g1.sort_order == 9


class TestMetricView:
    def test_list_and_set_order(self, api_client):
        obj = MonitorObject.objects.create(name="MViewObj", level="base")
        plugin = MonitorPlugin.objects.create(name="MViewPlugin")
        group = MetricGroup.objects.create(monitor_object=obj, monitor_plugin=plugin, name="g")
        m = Metric.objects.create(
            monitor_object=obj,
            monitor_plugin=plugin,
            metric_group=group,
            name="cpu",
            display_name="CPU",
            description="d",
            sort_order=3,
        )
        resp = api_client.get(f"{BASE}/api/metrics/?monitor_object_id={obj.id}")
        assert resp.status_code == 200
        assert any(item["name"] == "cpu" for item in resp.json()["data"])

        resp2 = api_client.post(f"{BASE}/api/metrics/set_order/", [{"id": m.id, "sort_order": 7}], format="json")
        assert resp2.status_code == 200
        m.refresh_from_db()
        assert m.sort_order == 7


class TestMonitorConditionView:
    def test_list_filters_by_permission(self, api_client, mocker):
        api_client.cookies["current_team"] = "1"
        _patch_current_team_scope(mocker)
        mocker.patch(
            "apps.monitor.views.monitor_condition.get_permission_rules",
            return_value={"team": [1], "instance": []},
        )
        cond = MonitorCondition.objects.create(name="c1", condition={})
        MonitorConditionOrganization.objects.create(monitor_condition=cond, organization=1)
        resp = api_client.get(f"{BASE}/api/monitor_condition/")
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["count"] >= 1
        assert any(item["name"] == "c1" for item in body["items"])

    def test_create_with_organizations(self, api_client, mocker):
        api_client.cookies["current_team"] = "1"
        _patch_current_team_scope(mocker, assignable=(1, 3, 4))
        resp = api_client.post(
            f"{BASE}/api/monitor_condition/",
            {"name": "newc", "condition": {"x": 1}, "organizations": [3, 4]},
            format="json",
        )
        assert resp.status_code in (200, 201)
        cond = MonitorCondition.objects.get(name="newc")
        orgs = set(MonitorConditionOrganization.objects.filter(monitor_condition_id=cond.id).values_list("organization", flat=True))
        assert orgs == {3, 4}

    def test_destroy_cleans_organizations(self, api_client, mocker):
        api_client.cookies["current_team"] = "1"
        _patch_current_team_scope(mocker)
        cond = MonitorCondition.objects.create(name="delc", condition={})
        MonitorConditionOrganization.objects.create(monitor_condition=cond, organization=1)
        mocker.patch(
            "apps.monitor.views.monitor_condition.get_permission_rules",
            return_value={"team": [], "instance": [{"id": cond.id, "permission": ["View", "Operate"]}]},
        )
        resp = api_client.delete(f"{BASE}/api/monitor_condition/{cond.id}/")
        assert resp.status_code in (200, 204)
        assert not MonitorCondition.objects.filter(id=cond.id).exists()
        assert not MonitorConditionOrganization.objects.filter(monitor_condition_id=cond.id).exists()


class TestNodeMgmtView:
    def test_get_nodes_calls_node_mgmt(self, api_client, mocker):
        api_client.cookies["current_team"] = "1"
        _patch_current_team_scope(mocker)
        node_mgmt = mocker.patch("apps.monitor.views.node_mgmt.NodeMgmt")
        node_mgmt.return_value.node_list.return_value = {"count": 1, "nodes": [{"id": "n1"}]}
        resp = api_client.post(
            f"{BASE}/api/node_mgmt/nodes/",
            {"cloud_region_id": 1, "page": 1, "page_size": 10},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["count"] == 1
        query = node_mgmt.return_value.node_list.call_args.args[0]
        assert query["cloud_region_id"] == 1
        assert query["page"] == 1 and query["page_size"] == 10

    def test_get_config_content(self, api_client, mocker):
        api_client.cookies["current_team"] = "1"
        _patch_current_team_scope(mocker)
        svc = mocker.patch(
            "apps.monitor.views.node_mgmt.InstanceConfigService.get_config_content",
            return_value=[{"id": "c1", "content": "x"}],
        )
        resp = api_client.post(
            f"{BASE}/api/node_mgmt/get_config_content/",
            {"ids": ["c1"]},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.json()["data"] == [{"id": "c1", "content": "x"}]
        svc.assert_called_once()

    def test_missing_current_team_errors(self, api_client, mocker):
        # cookie/header 无 current_team → _build_actor_context 抛 BaseAppException
        resp = api_client.post(
            f"{BASE}/api/node_mgmt/get_config_content/",
            {"ids": ["c1"]},
            format="json",
        )
        # 默认 user current_team 来自 cookie，缺失时返回非 2xx
        assert resp.status_code != 200 or resp.json().get("result") is not True
