import json
import types

from apps.monitor.models.collect_config import CollectConfig
from apps.monitor.models.monitor_object import MonitorInstance, MonitorObject
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.views import monitor_instance as monitor_instance_view


def test_remove_monitor_instance_refreshes_flow_cloud_regions(db, monkeypatch):
    monitor_object = MonitorObject.objects.create(name="Switch", display_name="Switch")
    instance = MonitorInstance.objects.create(
        id="('flow-device-1',)",
        name="Core Switch",
        monitor_object_id=monitor_object.id,
        cloud_region_id=3,
        ip="10.0.0.12",
        enabled_protocols=["netflow"],
    )
    refresh_calls = []

    monkeypatch.setattr(monitor_instance_view, "_build_actor_context", lambda request: {"current_team": 1})
    monkeypatch.setattr(monitor_instance_view, "_ensure_operate_instances", lambda request, instance_ids, actor_context=None: instance_ids)
    monkeypatch.setattr(monitor_instance_view, "cleanup_policy_sources", lambda instance_ids: None)
    monkeypatch.setattr(
        monitor_instance_view,
        "NodeMgmt",
        lambda: types.SimpleNamespace(delete_child_configs=lambda ids: None, delete_configs=lambda ids: None),
    )
    monkeypatch.setattr(
        "apps.monitor.services.flow_onboarding.FlowOnboardingService._schedule_region_refresh",
        lambda *region_ids: refresh_calls.append(region_ids),
    )

    request = types.SimpleNamespace(
        data={"instance_ids": [instance.id], "clean_child_config": False},
        COOKIES={"current_team": "1"},
        user=types.SimpleNamespace(username="tester", domain="default", is_superuser=True, group_list=[]),
    )

    monitor_instance_view.MonitorInstanceViewSet().remove_monitor_instance(request)

    instance.refresh_from_db()
    assert instance.is_deleted is True
    assert refresh_calls == [(3,)]


def test_remove_monitor_instance_registers_refresh_before_cleanup(db, monkeypatch):
    monitor_object = MonitorObject.objects.create(name="Switch", display_name="Switch")
    instance = MonitorInstance.objects.create(
        id="('flow-device-2',)",
        name="Edge Switch",
        monitor_object_id=monitor_object.id,
        cloud_region_id=5,
        ip="10.0.0.22",
        enabled_protocols=["sflow"],
    )
    refresh_calls = []

    monkeypatch.setattr(monitor_instance_view, "_build_actor_context", lambda request: {"current_team": 1})
    monkeypatch.setattr(monitor_instance_view, "_ensure_operate_instances", lambda request, instance_ids, actor_context=None: instance_ids)
    monkeypatch.setattr(
        monitor_instance_view,
        "NodeMgmt",
        lambda: types.SimpleNamespace(delete_child_configs=lambda ids: None, delete_configs=lambda ids: None),
    )
    monkeypatch.setattr(
        "apps.monitor.services.flow_onboarding.FlowOnboardingService._schedule_region_refresh",
        lambda *region_ids: refresh_calls.append(region_ids),
    )
    monkeypatch.setattr(
        monitor_instance_view,
        "cleanup_policy_sources",
        lambda instance_ids: (_ for _ in ()).throw(RuntimeError("cleanup failed")),
    )

    request = types.SimpleNamespace(
        data={"instance_ids": [instance.id], "clean_child_config": False},
        COOKIES={"current_team": "1"},
        user=types.SimpleNamespace(username="tester", domain="default", is_superuser=True, group_list=[]),
    )

    try:
        monitor_instance_view.MonitorInstanceViewSet().remove_monitor_instance(request)
        assert False, "expected cleanup failure"
    except RuntimeError as error:
        assert str(error) == "cleanup failed"

    instance.refresh_from_db()
    assert instance.is_deleted is True
    assert refresh_calls == [(5,)]


def test_remove_monitor_instance_always_cleans_configs(db, monkeypatch):
    monitor_object = MonitorObject.objects.create(name="Host", display_name="Host")
    instance = MonitorInstance.objects.create(
        id="('host-1',)",
        name="Host-1",
        monitor_object_id=monitor_object.id,
    )
    child_config = CollectConfig.objects.create(
        id="child-cfg",
        monitor_instance=instance,
        collector="Telegraf",
        collect_type="host",
        config_type="cpu",
        file_type="toml",
        is_child=True,
    )
    base_config = CollectConfig.objects.create(
        id="base-cfg",
        monitor_instance=instance,
        collector="Telegraf",
        collect_type="host-base",
        config_type="agent",
        file_type="toml",
        is_child=False,
    )
    cleanup_calls = {"child": None, "base": None}

    monkeypatch.setattr(monitor_instance_view, "_build_actor_context", lambda request: {"current_team": 1})
    monkeypatch.setattr(monitor_instance_view, "_ensure_operate_instances", lambda request, instance_ids, actor_context=None: instance_ids)
    monkeypatch.setattr(monitor_instance_view, "cleanup_policy_sources", lambda instance_ids: None)
    monkeypatch.setattr(
        monitor_instance_view,
        "NodeMgmt",
        lambda: types.SimpleNamespace(
            delete_child_configs=lambda ids: cleanup_calls.__setitem__("child", ids),
            delete_configs=lambda ids: cleanup_calls.__setitem__("base", ids),
        ),
    )

    request = types.SimpleNamespace(
        data={"instance_ids": [instance.id], "clean_child_config": False},
        COOKIES={"current_team": "1"},
        user=types.SimpleNamespace(username="tester", domain="default", is_superuser=True, group_list=[]),
    )

    monitor_instance_view.MonitorInstanceViewSet().remove_monitor_instance(request)

    instance.refresh_from_db()
    assert instance.is_deleted is True
    assert cleanup_calls == {"child": [child_config.id], "base": [base_config.id]}
    assert CollectConfig.objects.filter(monitor_instance_id=instance.id).count() == 0


def _create_effective_plugin_fixture():
    monitor_object = MonitorObject.objects.create(
        name="Host",
        display_name="Host",
        instance_id_keys=["instance_id"],
    )
    instance = MonitorInstance.objects.create(
        id="('host-a',)",
        name="Host A",
        monitor_object=monitor_object,
    )
    configured_plugin = MonitorPlugin.objects.create(
        name="HostRemote",
        display_name="Host Remote",
        template_id="hostremote",
        template_type="pull",
        collector="Telegraf",
        collect_type="http",
        status_query="any({plugin_id='hostremote'}) by (instance_id)",
        is_pre=False,
    )
    configured_plugin.monitor_object.add(monitor_object)
    reported_plugin = MonitorPlugin.objects.create(
        name="HostApi",
        display_name="Host API",
        template_id="hostapi",
        template_type="api",
        collector="push_api",
        collect_type="push_api",
        status_query="any({plugin_id='hostapi'}) by (instance_id)",
        is_pre=False,
    )
    reported_plugin.monitor_object.add(monitor_object)
    unused_plugin = MonitorPlugin.objects.create(
        name="HostUnused",
        display_name="Host Unused",
        template_id="hostunused",
        template_type="api",
        collector="push_api",
        collect_type="push_api",
        status_query="any({plugin_id='hostunused'}) by (instance_id)",
        is_pre=False,
    )
    unused_plugin.monitor_object.add(monitor_object)
    CollectConfig.objects.create(
        id="hostremote-cfg",
        monitor_instance=instance,
        monitor_plugin=configured_plugin,
        collector="Telegraf",
        collect_type="http",
        config_type="hostremote",
        file_type="toml",
        is_child=True,
    )
    return monitor_object, instance, configured_plugin, reported_plugin, unused_plugin


def test_effective_plugins_service_merges_configured_and_reported_plugins(db, monkeypatch):
    from apps.monitor.services import effective_plugins

    monitor_object, instance, configured_plugin, reported_plugin, unused_plugin = _create_effective_plugin_fixture()

    class StubVictoriaMetricsAPI:
        def query(self, query, step="5m", time=None):
            if "hostremote" in query:
                return {"data": {"result": []}}
            if "hostapi" in query:
                return {"data": {"result": [{"metric": {"instance_id": "host-a"}, "value": [100, "1"]}]}}
            if "hostunused" in query:
                return {"data": {"result": [{"metric": {"instance_id": "host-b"}, "value": [100, "1"]}]}}
            return {"data": {"result": []}}

    monkeypatch.setattr(effective_plugins, "VictoriaMetricsAPI", StubVictoriaMetricsAPI)

    result = effective_plugins.MonitorEffectivePluginService.get_effective_plugins(
        monitor_object.id,
        instance.id,
        locale="zh-Hans",
    )

    by_name = {item["name"]: item for item in result}
    assert set(by_name) == {"HostRemote", "HostApi"}
    assert by_name["HostRemote"]["id"] == configured_plugin.id
    assert by_name["HostRemote"]["status"] == "offline"
    assert by_name["HostRemote"]["collect_mode"] == "auto"
    assert by_name["HostApi"]["id"] == reported_plugin.id
    assert by_name["HostApi"]["status"] == "normal"
    assert by_name["HostApi"]["collect_mode"] == "manual"
    assert unused_plugin.name not in by_name


def test_effective_plugins_service_deduplicates_configured_reported_plugin(db, monkeypatch):
    from apps.monitor.services import effective_plugins

    monitor_object, instance, configured_plugin, _, _ = _create_effective_plugin_fixture()

    class StubVictoriaMetricsAPI:
        def query(self, query, step="5m", time=None):
            if "hostremote" in query:
                return {"data": {"result": [{"metric": {"instance_id": "host-a"}, "value": [100, "1"]}]}}
            return {"data": {"result": []}}

    monkeypatch.setattr(effective_plugins, "VictoriaMetricsAPI", StubVictoriaMetricsAPI)

    result = effective_plugins.MonitorEffectivePluginService.get_effective_plugins(
        monitor_object.id,
        instance.id,
        locale="zh-Hans",
    )

    by_name = {item["name"]: item for item in result}
    assert list(by_name) == ["HostRemote"]
    assert by_name["HostRemote"]["id"] == configured_plugin.id
    assert by_name["HostRemote"]["status"] == "normal"
    assert by_name["HostRemote"]["collect_mode"] == "auto"


def test_primary_object_plugin_list_keeps_builtin_plugins_distinct_by_plugin_id(db, monkeypatch):
    from apps.monitor.constants.plugin import PluginConstants
    from apps.monitor.services import monitor_instance

    monitor_object = MonitorObject.objects.create(
        name="Host",
        display_name="Host",
        instance_id_keys=["instance_id"],
    )
    instance = MonitorInstance.objects.create(
        id="('host-a',)",
        name="Host A",
        monitor_object=monitor_object,
    )
    remote_plugin = MonitorPlugin.objects.create(
        name="Host Remote",
        display_name="Host Remote",
        template_id="host",
        template_type="builtin",
        collector="Telegraf",
        collect_type="http",
        status_query="any({config_type='host'}) by (instance_id)",
        is_pre=True,
    )
    remote_plugin.monitor_object.add(monitor_object)
    windows_plugin = MonitorPlugin.objects.create(
        name="Windows WMI",
        display_name="Windows WMI",
        template_id="windows_wmi",
        template_type="builtin",
        collector="Telegraf",
        collect_type="http",
        status_query="any({config_type='windows_wmi'}) by (instance_id)",
        is_pre=True,
    )
    windows_plugin.monitor_object.add(monitor_object)
    CollectConfig.objects.create(
        id="windows-wmi-cfg",
        monitor_instance=instance,
        monitor_plugin=windows_plugin,
        collector="Telegraf",
        collect_type="http",
        config_type="windows_wmi",
        file_type="toml",
        is_child=True,
    )

    class StubVictoriaMetricsAPI:
        def query(self, query, step="5m", time=None):
            if "config_type='host'" in query:
                return {"data": {"result": [{"metric": {"instance_id": "host-a"}, "value": [100, "1"]}]}}
            return {"data": {"result": []}}

    monkeypatch.setattr(monitor_instance, "VictoriaMetricsAPI", StubVictoriaMetricsAPI)

    result = monitor_instance.InstanceSearch(
        monitor_object,
        {"page": 1, "page_size": 10},
        qs=MonitorInstance.objects.all(),
        locale="zh-Hans",
    ).search_by_primary_object()

    plugins = result["results"][0]["plugins"]
    by_name = {item["name"]: item for item in plugins}

    assert set(by_name) == {"Host Remote", "Windows WMI"}
    assert by_name["Host Remote"]["status"] == PluginConstants.STATUS_NORMAL
    assert by_name["Host Remote"]["collect_mode"] == PluginConstants.COLLECT_MODE_MANUAL
    assert by_name["Windows WMI"]["status"] == PluginConstants.STATUS_OFFLINE
    assert by_name["Windows WMI"]["collect_mode"] == PluginConstants.COLLECT_MODE_AUTO


def test_primary_object_plugin_list_shows_configured_host_remote_not_wmi(db, monkeypatch):
    from apps.monitor.constants.plugin import PluginConstants
    from apps.monitor.services import monitor_instance

    monitor_object = MonitorObject.objects.create(
        name="Host",
        display_name="Host",
        instance_id_keys=["instance_id"],
    )
    instance = MonitorInstance.objects.create(
        id="('host-a',)",
        name="Host A",
        monitor_object=monitor_object,
    )
    remote_plugin = MonitorPlugin.objects.create(
        name="Host Remote",
        display_name="Host Remote",
        template_id="host",
        template_type="builtin",
        collector="Telegraf",
        collect_type="http",
        status_query="any({config_type='host'}) by (instance_id)",
        is_pre=True,
    )
    remote_plugin.monitor_object.add(monitor_object)
    windows_plugin = MonitorPlugin.objects.create(
        name="Windows WMI",
        display_name="Windows WMI",
        template_id="windows_wmi",
        template_type="builtin",
        collector="Telegraf",
        collect_type="http",
        status_query="any({config_type='windows_wmi'}) by (instance_id)",
        is_pre=True,
    )
    windows_plugin.monitor_object.add(monitor_object)
    CollectConfig.objects.create(
        id="host-remote-cfg",
        monitor_instance=instance,
        monitor_plugin=remote_plugin,
        collector="Telegraf",
        collect_type="http",
        config_type="host",
        file_type="toml",
        is_child=True,
    )

    class StubVictoriaMetricsAPI:
        def query(self, query, step="5m", time=None):
            if "config_type='host'" in query:
                return {"data": {"result": [{"metric": {"instance_id": "host-a"}, "value": [100, "1"]}]}}
            return {"data": {"result": []}}

    monkeypatch.setattr(monitor_instance, "VictoriaMetricsAPI", StubVictoriaMetricsAPI)

    result = monitor_instance.InstanceSearch(
        monitor_object,
        {"page": 1, "page_size": 10},
        qs=MonitorInstance.objects.all(),
        locale="zh-Hans",
    ).search_by_primary_object()

    plugins = result["results"][0]["plugins"]

    assert len(plugins) == 1
    assert plugins[0]["name"] == "Host Remote"
    assert plugins[0]["status"] == PluginConstants.STATUS_NORMAL
    assert plugins[0]["collect_mode"] == PluginConstants.COLLECT_MODE_AUTO


def test_primary_object_plugin_list_deduplicates_flow_configured_and_reported_plugin(db, monkeypatch):
    from apps.monitor.constants.plugin import PluginConstants
    from apps.monitor.services import monitor_instance

    monitor_object = MonitorObject.objects.create(
        name="Switch",
        display_name="Switch",
        default_metric="any({instance_type='switch'}) by (instance_id)",
        instance_id_keys=["instance_id"],
    )
    instance = MonitorInstance.objects.create(
        id="('flow:15:1:10.10.41.149',)",
        name="NetFlow-10.10.41.149",
        monitor_object=monitor_object,
        cloud_region_id=1,
        ip="10.10.41.149",
        enabled_protocols=["netflow"],
    )
    plugin = MonitorPlugin.objects.create(
        name="Switch Flow NetFlow",
        display_name="Switch Flow NetFlow",
        template_type="builtin",
        collector="Telegraf",
        collect_type="netflow",
        status_query="any({instance_type='switch', collect_type='netflow'}) by (instance_id)",
        is_pre=True,
    )
    plugin.monitor_object.add(monitor_object)
    CollectConfig.objects.create(
        id="switch-netflow-cfg",
        monitor_instance=instance,
        monitor_plugin=plugin,
        collector="Telegraf",
        collect_type="netflow",
        config_type="flow",
        file_type="toml",
        is_child=True,
    )

    class StubVictoriaMetricsAPI:
        def query(self, query, step="5m", time=None):
            return {
                "data": {
                    "result": [
                        {
                            "metric": {"instance_id": "flow:15:1:10.10.41.149"},
                            "value": [1781234567, "1"],
                        }
                    ]
                }
            }

    monkeypatch.setattr(monitor_instance, "VictoriaMetricsAPI", StubVictoriaMetricsAPI)

    result = monitor_instance.InstanceSearch(
        monitor_object,
        {"page": 1, "page_size": 10},
        qs=MonitorInstance.objects.all(),
        locale="zh-Hans",
    ).search_by_primary_object()

    plugins = result["results"][0]["plugins"]

    assert len(plugins) == 1
    assert plugins[0]["plugin_id"] == plugin.id
    assert plugins[0]["status"] == PluginConstants.STATUS_NORMAL
    assert plugins[0]["collect_mode"] == PluginConstants.COLLECT_MODE_AUTO


def test_effective_plugins_action_returns_service_data(monkeypatch):
    service_calls = {}
    expected = [{"id": 12, "name": "HostRemote"}]

    class StubService:
        @staticmethod
        def get_effective_plugins(monitor_object_id, instance_id, locale):
            service_calls["args"] = (monitor_object_id, instance_id, locale)
            return expected

    monkeypatch.setattr(monitor_instance_view, "_build_actor_context", lambda request: {"current_team": 1})
    monkeypatch.setattr(
        monitor_instance_view,
        "_ensure_operate_instances",
        lambda request, instance_ids, actor_context=None: instance_ids,
    )
    monkeypatch.setattr(monitor_instance_view, "MonitorEffectivePluginService", StubService)

    request = types.SimpleNamespace(
        GET={"instance_id": "('host-a',)"},
        COOKIES={"current_team": "1"},
        user=types.SimpleNamespace(
            username="tester",
            domain="default",
            locale="zh-Hans",
            is_superuser=True,
            group_list=[],
        ),
    )

    response = monitor_instance_view.MonitorInstanceViewSet().effective_plugins(request, "7")
    payload = json.loads(response.content)

    assert service_calls["args"] == (7, "('host-a',)", "zh-Hans")
    assert payload["data"] == expected
