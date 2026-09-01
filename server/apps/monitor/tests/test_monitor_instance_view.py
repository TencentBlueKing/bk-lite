import json
import threading
import time
import types

import pytest
import requests

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.current_team_scope import CurrentTeamDataScope
from apps.monitor.models.collect_config import CollectConfig
from apps.monitor.models.monitor_object import MonitorInstance, MonitorInstanceOrganization, MonitorObject
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.utils.dimension import build_safe_instance_id
from apps.monitor.views import monitor_instance as monitor_instance_view

NODE_MGMT_PATH = "apps.monitor.services.monitor_instance_removal.NodeMgmt"


def _superuser_actor_context():
    scope = CurrentTeamDataScope(1, frozenset({1}), False, "tester", "default", True)
    return {
        "is_superuser": True,
        "current_team": 1,
        "username": "tester",
        "domain": "default",
        "group_list": [],
        "include_children": False,
        "data_scope": scope,
    }


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
    monkeypatch.setattr(
        monitor_instance_view,
        "_ensure_operate_instances",
        lambda request, instance_ids, actor_context=None, allow_missing=False: instance_ids,
    )
    monkeypatch.setattr(
        NODE_MGMT_PATH,
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

    assert not MonitorInstance.objects.filter(id=instance.id).exists()
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
    monkeypatch.setattr(
        monitor_instance_view,
        "_ensure_operate_instances",
        lambda request, instance_ids, actor_context=None, allow_missing=False: instance_ids,
    )
    monkeypatch.setattr(
        NODE_MGMT_PATH,
        lambda: types.SimpleNamespace(delete_child_configs=lambda ids: None, delete_configs=lambda ids: None),
    )
    monkeypatch.setattr(
        "apps.monitor.services.flow_onboarding.FlowOnboardingService._schedule_region_refresh",
        lambda *region_ids: refresh_calls.append(region_ids),
    )
    monkeypatch.setattr(
        "apps.monitor.services.monitor_instance_removal.cleanup_policy_sources",
        lambda instance_ids: (_ for _ in ()).throw(RuntimeError("cleanup failed")),
    )

    request = types.SimpleNamespace(
        data={"instance_ids": [instance.id], "clean_child_config": False},
        COOKIES={"current_team": "1"},
        user=types.SimpleNamespace(username="tester", domain="default", is_superuser=True, group_list=[]),
    )

    with pytest.raises(BaseAppException) as exc_info:
        monitor_instance_view.MonitorInstanceViewSet().remove_monitor_instance(request)

    instance.refresh_from_db()
    assert instance.is_deleted is False
    assert "删除监控实例失败" in str(exc_info.value)
    assert refresh_calls == []


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
    monkeypatch.setattr(
        monitor_instance_view,
        "_ensure_operate_instances",
        lambda request, instance_ids, actor_context=None, allow_missing=False: instance_ids,
    )
    monkeypatch.setattr(
        NODE_MGMT_PATH,
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

    assert not MonitorInstance.objects.filter(id=instance.id).exists()
    assert cleanup_calls == {"child": [child_config.id], "base": [base_config.id]}
    assert CollectConfig.objects.filter(monitor_instance_id=instance.id).count() == 0


def test_remove_monitor_instance_passes_manual_lifecycle_context(db, monkeypatch):
    remove_calls = []
    monkeypatch.setattr(
        monitor_instance_view,
        "_build_actor_context",
        lambda request: {"current_team": 1, "username": "page-operator"},
    )
    monkeypatch.setattr(
        monitor_instance_view,
        "_ensure_operate_instances",
        lambda request, instance_ids, actor_context=None, allow_missing=False: instance_ids,
    )
    monkeypatch.setattr(
        monitor_instance_view.MonitorInstanceRemovalService,
        "remove",
        lambda instance_ids, **kwargs: remove_calls.append((instance_ids, kwargs)),
    )
    request = types.SimpleNamespace(
        data={"instance_ids": ["manual-instance"]},
        user=types.SimpleNamespace(username="fallback-operator"),
    )

    monitor_instance_view.MonitorInstanceViewSet().remove_monitor_instance(request)

    assert remove_calls == [
        (
            ["manual-instance"],
            {
                "operator": "page-operator",
                "reason": "manual_instance_deleted",
            },
        )
    ]


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
                return {"data": {"result": [{"metric": {"instance_id": "host-a"}, "value": [1782888110, "1782888000"]}]}}
            if "hostunused" in query:
                return {"data": {"result": [{"metric": {"instance_id": "host-b"}, "value": [1782888110, "1782888000"]}]}}
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
                return {"data": {"result": [{"metric": {"instance_id": "host-a"}, "value": [1782888110, "1782888000"]}]}}
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


def test_effective_plugins_service_deduplicates_status_queries_with_bounded_concurrency(db, monkeypatch):
    from apps.monitor.services import effective_plugins

    monitor_object = MonitorObject.objects.create(
        name="EffectivePluginBatch",
        display_name="Effective Plugin Batch",
        instance_id_keys=["instance_id"],
    )
    for index in range(10):
        plugin = MonitorPlugin.objects.create(
            name=f"BatchPlugin{index}",
            status_query=f'any({{kind="{index % 5}"}}) by (instance_id)',
        )
        plugin.monitor_object.add(monitor_object)

    lock = threading.Lock()
    active = 0
    peak_active = 0
    calls = []

    class StubVictoriaMetricsAPI:
        def query(self, query, **kwargs):
            nonlocal active, peak_active
            with lock:
                calls.append(query)
                active += 1
                peak_active = max(peak_active, active)
            time.sleep(0.03)
            with lock:
                active -= 1
            if 'kind="4"' in query:
                raise RuntimeError("one plugin status unavailable")
            return {"data": {"result": [{"metric": {"instance_id": "host-a"}, "value": [1782888110, "1782888000"]}]}}

    monkeypatch.setattr(effective_plugins, "VictoriaMetricsAPI", StubVictoriaMetricsAPI)

    result = effective_plugins.MonitorEffectivePluginService.get_effective_plugins(
        monitor_object.id,
        "('host-a',)",
    )

    assert len(result) == 8
    assert len(calls) == 5
    assert len(set(calls)) == 5
    assert 1 < peak_active <= 8


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [(None, 8), ("invalid", 8), ("0", 1), ("-1", 1), ("1000", 32)],
)
def test_vm_query_worker_config_is_safe_and_bounded(monkeypatch, raw_value, expected):
    from apps.monitor.utils import vm_query_batch

    if raw_value is None:
        monkeypatch.delenv("MONITOR_VM_QUERY_MAX_WORKERS", raising=False)
    else:
        monkeypatch.setenv("MONITOR_VM_QUERY_MAX_WORKERS", raw_value)

    assert vm_query_batch._resolve_vm_query_max_workers() == expected


def test_vm_query_batch_worker_one_is_serial_and_timeout_is_isolated(monkeypatch):
    from apps.monitor.utils import vm_query_batch

    monkeypatch.setattr(vm_query_batch, "VM_QUERY_MAX_WORKERS", 1)
    active = 0
    peak_active = 0

    def query(query_text):
        nonlocal active, peak_active
        active += 1
        peak_active = max(peak_active, active)
        try:
            if query_text == "timeout":
                raise requests.Timeout("VM query timed out")
            time.sleep(0.01)
            return query_text.upper()
        finally:
            active -= 1

    results, errors = vm_query_batch.run_unique_vm_queries(
        ["first", "timeout", "first", "last"],
        query,
    )

    assert results == {"first": "FIRST", "last": "LAST"}
    assert isinstance(errors["timeout"], requests.Timeout)
    assert peak_active == 1


def test_effective_plugins_service_resolves_derived_instance_without_row(db, monkeypatch):
    # 回归：K8s Pod/Node 等派生实例在指标里上报，但没有自己的 MonitorInstance 行。
    # 修复前 get_effective_plugins 强制要求实例行，缺失即抛 "Monitor instance does not exist"（500）。
    # 修复后无行也能基于上报指标解析有效插件，不再抛异常。
    from apps.monitor.services import effective_plugins

    monitor_object = MonitorObject.objects.create(
        name="Pod",
        display_name="Pod",
        instance_id_keys=["instance_id"],
    )
    reported_plugin = MonitorPlugin.objects.create(
        name="K8sPod",
        display_name="K8s Pod",
        template_id="k8spod",
        template_type="api",
        collector="push_api",
        collect_type="push_api",
        status_query="any({plugin_id='k8spod'}) by (instance_id)",
        is_pre=False,
    )
    reported_plugin.monitor_object.add(monitor_object)

    derived_instance_id = "('derived-pod-x',)"
    # 该派生实例确实没有 MonitorInstance 行
    assert not MonitorInstance.objects.filter(id=derived_instance_id).exists()

    class StubVictoriaMetricsAPI:
        def query(self, query, step="5m", time=None):
            return {"data": {"result": [{"metric": {"instance_id": "derived-pod-x"}, "value": [1782888110, "1782888000"]}]}}

    monkeypatch.setattr(effective_plugins, "VictoriaMetricsAPI", StubVictoriaMetricsAPI)

    result = effective_plugins.MonitorEffectivePluginService.get_effective_plugins(
        monitor_object.id,
        derived_instance_id,
        locale="zh-Hans",
    )

    by_name = {item["name"]: item for item in result}
    assert "K8sPod" in by_name
    assert by_name["K8sPod"]["status"] == "normal"
    assert by_name["K8sPod"]["collect_mode"] == "manual"


def test_effective_plugins_service_matches_multi_key_derived_by_primary(db, monkeypatch):
    from apps.monitor.services import effective_plugins

    monitor_object = MonitorObject.objects.create(
        name="PodMultiKey",
        display_name="PodMultiKey",
        instance_id_keys=["instance_id", "pod"],
    )
    reported_plugin = MonitorPlugin.objects.create(
        name="K8S",
        display_name="K8S",
        template_id="k8s-mk",
        template_type="api",
        collector="push_api",
        collect_type="push_api",
        status_query="any({instance_type='k8s'}) by (instance_id)",
        is_pre=False,
    )
    reported_plugin.monitor_object.add(monitor_object)

    multi_key_instance_id = "('mac', 'coredns-abc')"

    class StubVictoriaMetricsAPI:
        def query(self, query, step="5m", time=None):
            return {"data": {"result": [{"metric": {"instance_id": "mac"}, "value": [1782888110, "1782888000"]}]}}

    monkeypatch.setattr(effective_plugins, "VictoriaMetricsAPI", StubVictoriaMetricsAPI)

    result = effective_plugins.MonitorEffectivePluginService.get_effective_plugins(
        monitor_object.id,
        multi_key_instance_id,
        locale="zh-Hans",
    )

    by_name = {item["name"]: item for item in result}
    assert "K8S" in by_name
    assert by_name["K8S"]["status"] == "normal"


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
                return {"data": {"result": [{"metric": {"instance_id": "host-a"}, "value": [1782888110, "1782888000"]}]}}
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
    assert by_name["Host Remote"]["configured"] is False
    assert by_name["Host Remote"]["config_source"] == "reported_only"
    assert by_name["Windows WMI"]["status"] == PluginConstants.STATUS_OFFLINE
    assert by_name["Windows WMI"]["collect_mode"] == PluginConstants.COLLECT_MODE_AUTO
    assert by_name["Windows WMI"]["configured"] is True
    assert by_name["Windows WMI"]["config_source"] == "configured"


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
                return {"data": {"result": [{"metric": {"instance_id": "host-a"}, "value": [1782888110, "1782888000"]}]}}
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
    assert plugins[0]["configured"] is True
    assert plugins[0]["config_source"] == "configured_reported"


def test_primary_object_plugin_list_deduplicates_flow_configured_and_reported_plugin(db, monkeypatch):
    from apps.monitor.constants.plugin import PluginConstants
    from apps.monitor.services import monitor_instance

    logical_id = build_safe_instance_id(1, "10.10.41.149")
    monitor_object = MonitorObject.objects.create(
        name="Switch",
        display_name="Switch",
        default_metric="any({instance_type='switch'}) by (instance_id)",
        instance_id_keys=["instance_id"],
    )
    instance = MonitorInstance.objects.create(
        id=str((logical_id,)),
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
                            "metric": {"instance_id": logical_id},
                            "value": [1781234567, "1781234500"],
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
    assert plugins[0]["configured"] is True
    assert plugins[0]["config_source"] == "configured_reported"


def test_primary_object_plugin_list_batches_and_aggregates_collection_nodes(db, monkeypatch):
    from apps.monitor.services import monitor_instance

    monitor_object = MonitorObject.objects.create(
        name="CollectionNodeHost",
        display_name="Collection Node Host",
        instance_id_keys=["instance_id"],
    )
    instance = MonitorInstance.objects.create(
        id="('host-a',)",
        name="Host A",
        monitor_object=monitor_object,
    )
    MonitorInstanceOrganization.objects.create(monitor_instance=instance, organization=7)
    automatic_plugin = MonitorPlugin.objects.create(
        name="AutomaticPlugin",
        display_name="Automatic Plugin",
        collector="Telegraf",
        collect_type="host",
        status_query="automatic_query",
    )
    automatic_plugin.monitor_object.add(monitor_object)
    manual_plugin = MonitorPlugin.objects.create(
        name="ManualPlugin",
        display_name="Manual Plugin",
        collector="push_api",
        collect_type="push_api",
        status_query="manual_query",
    )
    manual_plugin.monitor_object.add(monitor_object)
    unbound_plugin = MonitorPlugin.objects.create(
        name="UnboundPlugin",
        display_name="Unbound Plugin",
        collector="Telegraf",
        collect_type="disk",
        status_query="unbound_query",
    )
    unbound_plugin.monitor_object.add(monitor_object)
    for config_id, config_type in (("child-b", "mem"), ("child-a", "cpu")):
        CollectConfig.objects.create(
            id=config_id,
            monitor_instance=instance,
            monitor_plugin=automatic_plugin,
            collector="Telegraf",
            collect_type="host",
            config_type=config_type,
            file_type="toml",
            is_child=True,
        )
    CollectConfig.objects.create(
        id="child-unbound",
        monitor_instance=instance,
        monitor_plugin=unbound_plugin,
        collector="Telegraf",
        collect_type="disk",
        config_type="disk",
        file_type="toml",
        is_child=True,
    )

    class StubVictoriaMetricsAPI:
        def query(self, query, **kwargs):
            return {
                "data": {
                    "result": [
                        {
                            "metric": {"instance_id": "host-a"},
                            "value": [1782888110, "1782888000"],
                        }
                    ]
                }
            }

    calls = []

    class StubNodeMgmt:
        def get_child_config_nodes_by_ids(self, ids, organization_ids):
            calls.append((ids, organization_ids))
            return [
                {
                    "id": "child-a",
                    "nodes": [
                        {"id": "node-2", "name": "Beta"},
                        {"id": "node-1", "name": "Alpha"},
                    ],
                },
                {
                    "id": "child-b",
                    "nodes": [
                        {"id": "node-1", "name": "Alpha"},
                    ],
                },
            ]

    monkeypatch.setattr(monitor_instance, "VictoriaMetricsAPI", StubVictoriaMetricsAPI)
    monkeypatch.setattr(monitor_instance, "NodeMgmt", StubNodeMgmt)

    result = monitor_instance.InstanceSearch(
        monitor_object,
        {"page": 1, "page_size": 10},
        qs=MonitorInstance.objects.all(),
        locale="zh-Hans",
        visible_organization_ids=frozenset({7}),
    ).search_by_primary_object()

    assert calls == [(["child-a", "child-b", "child-unbound"], [7])]
    plugins = {plugin["name"]: plugin for plugin in result["results"][0]["plugins"]}
    assert plugins["AutomaticPlugin"]["collector_nodes"] == [
        {"id": "node-1", "name": "Alpha"},
        {"id": "node-2", "name": "Beta"},
    ]
    assert plugins["UnboundPlugin"]["collector_nodes"] == []
    assert plugins["ManualPlugin"]["collector_nodes"] == []


def test_get_instance_configs_uses_plugin_id_over_collector_for_child_configs(db, monkeypatch):
    from apps.monitor.services import node_mgmt

    monitor_object = MonitorObject.objects.create(
        name="Oracle",
        display_name="Oracle",
        instance_id_keys=["instance_id"],
    )
    instance = MonitorInstance.objects.create(
        id="('oracle-a',)",
        name="Oracle A",
        monitor_object=monitor_object,
    )
    plugin = MonitorPlugin.objects.create(
        name="Oracle-Exporter",
        display_name="Oracle Exporter",
        collector="Oracle-Exporter",
        collect_type="exporter",
    )
    plugin.monitor_object.add(monitor_object)
    config = CollectConfig.objects.create(
        id="oracle-child-cfg",
        monitor_instance=instance,
        monitor_plugin=plugin,
        collector="Telegraf",
        collect_type="exporter",
        config_type="oracle",
        file_type="toml",
        is_child=True,
    )

    monkeypatch.setattr(
        node_mgmt.InstanceConfigService,
        "get_config_content",
        staticmethod(lambda ids, actor_context=None: {"child": {"id": ids[0], "env_config": {}}}),
    )

    result = node_mgmt.InstanceConfigService.get_instance_configs(
        instance.id,
        monitor_plugin_id=plugin.id,
        collector="Oracle-Exporter",
        collect_type="exporter",
    )

    assert len(result) == 1
    assert result[0]["config_ids"] == [config.id]
    assert result[0]["monitor_plugin_id"] == plugin.id


def test_validate_expected_collect_configs_raises_when_metadata_missing(db):
    from apps.core.exceptions.base_app_exception import BaseAppException
    from apps.monitor.services import node_mgmt

    monitor_object = MonitorObject.objects.create(
        name="Oracle",
        display_name="Oracle",
        instance_id_keys=["instance_id"],
    )
    instance = MonitorInstance.objects.create(
        id="('oracle-a',)",
        name="Oracle A",
        monitor_object=monitor_object,
    )
    plugin = MonitorPlugin.objects.create(
        name="Oracle-Exporter",
        display_name="Oracle Exporter",
        collector="Oracle-Exporter",
        collect_type="exporter",
    )
    plugin.monitor_object.add(monitor_object)

    try:
        node_mgmt.InstanceConfigService._validate_expected_collect_configs(
            [{"instance_id": instance.id}],
            [{"type": "oracle"}],
            plugin.id,
            "exporter",
        )
        assert False, "expected missing collect config metadata to fail"
    except BaseAppException as error:
        assert "采集配置元数据缺失" in str(error)
        assert f"{instance.id}:oracle" in str(error)


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
        lambda request, instance_ids, actor_context=None, allow_missing=False: instance_ids,
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


def test_effective_plugins_action_normalizes_clean_instance_id(db, monkeypatch):
    """前端传干净标量(如 "host-a"),实例在库中存为元组串 "('host-a',)"。

    视图必须把入参归一为存储键形态再做存在性校验与服务调用,否则误报"监控实例不存在"
    (回归自 fbc8ef34a「feat: filter monitor view plugins by reported data」)。
    """
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
    MonitorInstanceOrganization.objects.create(monitor_instance=instance, organization=1)

    service_calls = {}
    expected = [{"id": 12, "name": "HostRemote"}]

    class StubService:
        @staticmethod
        def get_effective_plugins(monitor_object_id, instance_id, locale):
            service_calls["args"] = (monitor_object_id, instance_id, locale)
            return expected

    monkeypatch.setattr(monitor_instance_view, "MonitorEffectivePluginService", StubService)
    # 仅 mock actor_context，保留真实 _ensure_operate_instances 以触发存在性与 current_team 查询。
    monkeypatch.setattr(
        monitor_instance_view,
        "_build_actor_context",
        lambda request: _superuser_actor_context(),
    )

    request = types.SimpleNamespace(
        GET={"instance_id": "host-a"},  # 前端下传的是干净标量,而非存储用的元组串
        COOKIES={"current_team": "1"},
        user=types.SimpleNamespace(
            username="tester",
            domain="default",
            locale="zh-Hans",
            is_superuser=True,
            group_list=[],
        ),
    )

    response = monitor_instance_view.MonitorInstanceViewSet().effective_plugins(request, str(monitor_object.id))
    payload = json.loads(response.content)

    assert service_calls["args"] == (monitor_object.id, "('host-a',)", "zh-Hans")
    assert payload["data"] == expected


def test_effective_plugins_action_allows_derived_instance_without_row(db, monkeypatch):
    # 回归：K8s Pod/Node 等派生实例没有 MonitorInstance 行。视图层 _ensure_operate_instances
    # 修复前对无行实例抛 "监控实例不存在"（500，先于 service）；修复后以 allow_missing=True 放行，
    # 详情页据上报指标解析插件并返回 200，而非 500。
    monitor_object = MonitorObject.objects.create(
        name="Pod",
        display_name="Pod",
        instance_id_keys=["instance_id"],
    )
    derived_instance_id = "('derived-pod-x',)"
    assert not MonitorInstance.objects.filter(id=derived_instance_id).exists()

    expected = [{"id": 7, "name": "K8sPod"}]

    class StubService:
        @staticmethod
        def get_effective_plugins(monitor_object_id, instance_id, locale):
            return expected

    monkeypatch.setattr(monitor_instance_view, "MonitorEffectivePluginService", StubService)
    # 超管 + 真实 _ensure_operate_instances，触发 current_team 路径（无行不再抛异常）。
    monkeypatch.setattr(
        monitor_instance_view,
        "_build_actor_context",
        lambda request: _superuser_actor_context(),
    )

    request = types.SimpleNamespace(
        GET={"instance_id": "derived-pod-x"},
        COOKIES={"current_team": "1"},
        user=types.SimpleNamespace(
            username="tester",
            domain="default",
            locale="zh-Hans",
            is_superuser=True,
            group_list=[],
        ),
    )

    response = monitor_instance_view.MonitorInstanceViewSet().effective_plugins(request, str(monitor_object.id))
    payload = json.loads(response.content)

    assert payload["data"] == expected


def test_effective_plugins_action_keeps_multi_dimension_instance_id(monkeypatch):
    """多维实例ID(如 VMware ESXi 的 instance_id+resource_id)不能被裁成单维。

    回归场景：详情页下传完整 tuple 串 "('vcenter-a', 'host-3171')"，如果视图把它归一成
    "('vcenter-a',)"，存在性校验与服务查询都会误报实例不存在。
    """
    service_calls = {}
    expected = [{"id": 88, "name": "VMWare"}]

    class StubService:
        @staticmethod
        def get_effective_plugins(monitor_object_id, instance_id, locale):
            service_calls["args"] = (monitor_object_id, instance_id, locale)
            return expected

    monkeypatch.setattr(monitor_instance_view, "MonitorEffectivePluginService", StubService)
    monkeypatch.setattr(
        monitor_instance_view,
        "_ensure_operate_instances",
        lambda request, instance_ids, actor_context=None, allow_missing=False: instance_ids,
    )
    monkeypatch.setattr(
        monitor_instance_view,
        "_build_actor_context",
        lambda request: {
            "is_superuser": True,
            "current_team": 1,
            "username": "tester",
            "domain": "default",
            "group_list": [],
            "include_children": False,
        },
    )

    request = types.SimpleNamespace(
        GET={"instance_id": "('vcenter-a', 'host-3171')"},
        COOKIES={"current_team": "1"},
        user=types.SimpleNamespace(
            username="tester",
            domain="default",
            locale="zh-Hans",
            is_superuser=True,
            group_list=[],
        ),
    )

    response = monitor_instance_view.MonitorInstanceViewSet().effective_plugins(request, "19")
    payload = json.loads(response.content)

    assert service_calls["args"] == (
        19,
        "('vcenter-a', 'host-3171')",
        "zh-Hans",
    )
    assert payload["data"] == expected


def test_monitor_instance_list_passes_normalized_instance_id(monkeypatch):
    """list 可选 instance_id：标量归一为存储键后再交给 service。"""
    captured = {}

    def fake_scope(request):
        return CurrentTeamDataScope(1, frozenset({1}), False, "tester", "default", True)

    def fake_get_monitor_instance(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {"count": 1, "results": [{"instance_id": "('h1',)", "instance_name": "主机1"}]}

    monkeypatch.setattr(monitor_instance_view, "resolve_current_team_data_scope", fake_scope)
    monkeypatch.setattr(
        monitor_instance_view,
        "get_permission_rules",
        lambda *args, **kwargs: {"team": [1], "instance": []},
    )
    monkeypatch.setattr(
        monitor_instance_view,
        "scope_permission_queryset",
        lambda *args, **kwargs: MonitorInstance.objects.none(),
    )
    monkeypatch.setattr(
        monitor_instance_view.MonitorObjectService,
        "get_monitor_instance",
        staticmethod(fake_get_monitor_instance),
    )

    request = types.SimpleNamespace(
        GET={"instance_id": "h1", "page": "1", "page_size": "1"},
        COOKIES={"current_team": "1"},
        user=types.SimpleNamespace(
            username="tester",
            domain="default",
            locale="zh-Hans",
            is_superuser=True,
            group_list=[],
        ),
    )
    response = monitor_instance_view.MonitorInstanceViewSet().monitor_instance_list(request, "19")
    payload = json.loads(response.content)

    assert captured["kwargs"]["instance_id"] == "('h1',)"
    assert payload["data"]["count"] == 1


def test_monitor_instance_list_invalid_instance_id_returns_empty(monkeypatch):
    monkeypatch.setattr(
        monitor_instance_view,
        "resolve_current_team_data_scope",
        lambda request: CurrentTeamDataScope(1, frozenset({1}), False, "tester", "default", True),
    )
    called = {"service": False}

    def boom(*args, **kwargs):
        called["service"] = True
        raise AssertionError("service should not run for invalid instance_id")

    monkeypatch.setattr(
        monitor_instance_view.MonitorObjectService,
        "get_monitor_instance",
        staticmethod(boom),
    )

    request = types.SimpleNamespace(
        GET={"instance_id": "()"},
        COOKIES={"current_team": "1"},
        user=types.SimpleNamespace(is_superuser=True, group_list=[]),
    )
    response = monitor_instance_view.MonitorInstanceViewSet().monitor_instance_list(request, "19")
    payload = json.loads(response.content)

    assert called["service"] is False
    assert payload["data"] == {"count": 0, "results": []}
