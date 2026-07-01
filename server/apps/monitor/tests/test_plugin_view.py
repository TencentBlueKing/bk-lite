"""MonitorPluginViewSet 视图规格测试。"""

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models import MonitorPlugin
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.views.plugin import MonitorPluginViewSet

pytestmark = pytest.mark.django_db

BASE = "/api/v1/monitor"


class TestEnsureModifiable:
    def test_builtin_plugin_raises(self):
        plugin = MonitorPlugin(name="x", is_pre=True)
        with pytest.raises(BaseAppException):
            MonitorPluginViewSet._ensure_modifiable(plugin)

    def test_custom_plugin_ok(self):
        plugin = MonitorPlugin(name="x", is_pre=False)
        assert MonitorPluginViewSet._ensure_modifiable(plugin) is None


class TestPluginList:
    def test_list_marks_custom_and_display(self, api_client):
        MonitorPlugin.objects.create(name="builtinp", template_type="builtin", description="d1")
        MonitorPlugin.objects.create(
            name="apip", template_type="api", display_name="API插件", description="d2",
        )
        resp = api_client.get(f"{BASE}/api/monitor_plugin/")
        assert resp.status_code == 200
        rows = {r["name"]: r for r in resp.json()["data"]}
        assert rows["apip"]["is_custom"] is True
        assert rows["apip"]["display_name"] == "API插件"
        assert rows["builtinp"]["is_custom"] is False


class TestGetAccessGuide:
    def test_non_api_template_errors(self, api_client):
        plugin = MonitorPlugin.objects.create(name="snmpp", template_type="snmp", template_id="t1")
        resp = api_client.get(f"{BASE}/api/monitor_plugin/{plugin.id}/access_guide/")
        body = resp.json()
        assert body.get("result") is False or resp.status_code != 200

    def test_api_template_returns_document(self, api_client, mocker):
        obj = MonitorObject.objects.create(name="AGObj", level="base", instance_id_keys=["instance_id"])
        plugin = MonitorPlugin.objects.create(
            name="apip2", template_type="api", template_id="t-api", display_name="API2",
        )
        plugin.monitor_object.add(obj)
        mocker.patch(
            "apps.monitor.services.template_access_guide.NodeMgmt"
        ).return_value.get_cloud_region_envconfig.return_value = {
            "NODE_SERVER_URL": "https://node.example.com:8080"
        }
        resp = api_client.get(
            f"{BASE}/api/monitor_plugin/{plugin.id}/access_guide/?organization_id=1&cloud_region_id=2"
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["template_id"] == "t-api"
        assert data["endpoint"].endswith("/telegraf/api")
