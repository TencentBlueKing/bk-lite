import json
import types

from apps.monitor.models.collect_config import CollectConfig
from apps.monitor.models.monitor_object import MonitorInstance, MonitorObject
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.utils.dimension import build_safe_instance_id
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
            return {"data": {"result": [{"metric": {"instance_id": "derived-pod-x"}, "value": [100, "1"]}]}}

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
    assert plugins[0]["configured"] is True
    assert plugins[0]["config_source"] == "configured_reported"


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
    MonitorInstance.objects.create(
        id="('host-a',)",
        name="Host A",
        monitor_object=monitor_object,
    )

    service_calls = {}
    expected = [{"id": 12, "name": "HostRemote"}]

    class StubService:
        @staticmethod
        def get_effective_plugins(monitor_object_id, instance_id, locale):
            service_calls["args"] = (monitor_object_id, instance_id, locale)
            return expected

    monkeypatch.setattr(monitor_instance_view, "MonitorEffectivePluginService", StubService)
    # 仅 mock actor_context(超管,跳过组织权限),保留真实 _ensure_operate_instances 以触发存在性查询。
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

    response = monitor_instance_view.MonitorInstanceViewSet().effective_plugins(
        request, str(monitor_object.id)
    )
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
    # 超管 + 真实 _ensure_operate_instances，触发存在性查询路径（无行不再抛异常）。
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

    response = monitor_instance_view.MonitorInstanceViewSet().effective_plugins(
        request, str(monitor_object.id)
    )
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

    response = monitor_instance_view.MonitorInstanceViewSet().effective_plugins(
        request, "19"
    )
    payload = json.loads(response.content)

    assert service_calls["args"] == (
        19,
        "('vcenter-a', 'host-3171')",
        "zh-Hans",
    )
    assert payload["data"] == expected
