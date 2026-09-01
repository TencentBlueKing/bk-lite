"""MonitorPluginViewSet 剩余：内置只读销毁、SNMP 删除、UI 模板、collect_template、导入导出。"""
import pytest
from django.db import ProgrammingError

from apps.monitor.models import MonitorPlugin, MonitorPluginUITemplate

pytestmark = pytest.mark.django_db
BASE = "/api/v1/monitor"


@pytest.fixture
def su_client(api_client, authenticated_user):
    authenticated_user.is_superuser = True
    authenticated_user.save(update_fields=["is_superuser"])
    return api_client


def test_destroy_builtin_plugin_rejected(su_client):
    plugin = MonitorPlugin.objects.create(name="pre-plugin", template_type="builtin", is_pre=True)
    resp = su_client.delete(f"{BASE}/api/monitor_plugin/{plugin.id}/")
    assert resp.status_code == 500
    assert resp.json()["result"] is False
    assert "只读" in resp.json()["message"]
    assert MonitorPlugin.objects.filter(id=plugin.id).exists()


def test_destroy_snmp_plugin_success_and_missing_column(su_client, mocker):
    plugin = MonitorPlugin.objects.create(name="snmp-del", template_type="snmp", is_pre=False)
    resp = su_client.delete(f"{BASE}/api/monitor_plugin/{plugin.id}/")
    assert resp.status_code == 200
    assert resp.json()["result"] is True
    assert not MonitorPlugin.objects.filter(id=plugin.id).exists()

    plugin2 = MonitorPlugin.objects.create(name="snmp-err", template_type="snmp", is_pre=False)
    mocker.patch.object(
        MonitorPlugin,
        "delete",
        side_effect=ProgrammingError('column "monitor_plugin_id" does not exist'),
    )
    resp = su_client.delete(f"{BASE}/api/monitor_plugin/{plugin2.id}/")
    assert resp.status_code == 500
    assert "monitor_collectconfig.monitor_plugin_id" in resp.json()["message"]


def test_get_ui_template_found_and_empty(su_client):
    plugin = MonitorPlugin.objects.create(
        name="ui-p",
        template_type="api",
        is_pre=False,
        node_selector={"os": "linux"},
        support_collect_detect=True,
    )
    empty = su_client.get(f"{BASE}/api/monitor_plugin/{plugin.id}/ui_template/")
    assert empty.status_code == 200
    assert empty.json()["data"] == {
        "ui_template": {},
        "node_selector": {"os": "linux"},
        "support_collect_detect": True,
    }
    MonitorPluginUITemplate.objects.create(plugin=plugin, content={"fields": [1]})
    found = su_client.get(f"{BASE}/api/monitor_plugin/{plugin.id}/ui_template/")
    assert found.json()["data"]["ui_template"] == {"fields": [1]}


def test_collect_template_requires_snmp_and_dispatches(su_client, mocker):
    api_plugin = MonitorPlugin.objects.create(name="api-ct", template_type="api", is_pre=False)
    bad = su_client.get(f"{BASE}/api/monitor_plugin/{api_plugin.id}/collect_template/")
    assert bad.status_code == 400
    assert bad.json()["message"] == "当前模板不是自建 SNMP 模板"

    snmp = MonitorPlugin.objects.create(name="snmp-ct", template_type="snmp", is_pre=False)
    mocker.patch(
        "apps.monitor.views.plugin.CustomSnmpPluginService.get_collect_template",
        return_value={"content": "oid"},
    )
    got = su_client.get(f"{BASE}/api/monitor_plugin/{snmp.id}/collect_template/")
    assert got.json()["data"] == {"content": "oid"}
    mocker.patch(
        "apps.monitor.views.plugin.CustomSnmpPluginService.update_collect_template",
        return_value={"content": "updated"},
    )
    put = su_client.put(
        f"{BASE}/api/monitor_plugin/{snmp.id}/collect_template/",
        {"content": "updated"},
        format="json",
    )
    assert put.json()["data"] == {"content": "updated"}


def test_import_and_export_delegate_to_service(su_client, mocker):
    importer = mocker.patch("apps.monitor.views.plugin.MonitorPluginService.import_monitor_plugin")
    exporter = mocker.patch(
        "apps.monitor.views.plugin.MonitorPluginService.export_monitor_plugin",
        return_value={"name": "p"},
    )
    plugin = MonitorPlugin.objects.create(name="exp", template_type="api", is_pre=False)
    imp = su_client.post(f"{BASE}/api/monitor_plugin/import/", {"name": "p"}, format="json")
    assert imp.status_code == 200
    importer.assert_called_once()
    exp = su_client.get(f"{BASE}/api/monitor_plugin/export/{plugin.id}/")
    assert exp.json()["data"] == {"name": "p"}
    exporter.assert_called_once_with(str(plugin.id))


def test_ensure_modifiable_used_on_update(su_client):
    plugin = MonitorPlugin.objects.create(name="upd-pre", template_type="builtin", is_pre=True)
    resp = su_client.put(
        f"{BASE}/api/monitor_plugin/{plugin.id}/",
        {"name": "upd-pre", "template_type": "builtin"},
        format="json",
    )
    assert resp.status_code == 500
    assert "只读" in resp.json()["message"]


def test_ui_template_by_params_delegates(su_client, mocker):
    mocker.patch(
        "apps.monitor.views.plugin.MonitorPluginService.get_ui_template_by_params",
        return_value={"ui": 1},
    )
    resp = su_client.get(f"{BASE}/api/monitor_plugin/ui_template_by_params/?collector=telegraf&collect_type=host&monitor_object_id=1")
    assert resp.json()["data"] == {
        "ui": 1,
        "ui_template": None,
        "support_collect_detect": False,
    }
