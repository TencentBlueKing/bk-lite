"""脚本挂到已有实例：多插件共存、网络设备身份、节点预填、列表圈选。"""

import pytest

from apps.monitor.models import CollectConfig, MonitorInstance, MonitorObject, MonitorPlugin
from apps.monitor.services.node_mgmt import InstanceConfigService
from apps.monitor.services.script_attach import bind_script_attach_instance_keys, fill_script_attach_collector_nodes, plugin_filter_membership
from apps.monitor.utils.plugin_controller import Controller

pytestmark = pytest.mark.django_db


def _object(name, keys=None):
    return MonitorObject.objects.create(
        name=name,
        level="base",
        instance_id_keys=keys if keys is not None else ["instance_id"],
    )


def _plugin(name, obj, collect_type="script"):
    plugin = MonitorPlugin.objects.create(
        name=name,
        collect_type=collect_type,
        collector="Telegraf",
        template_id=name,
        template_type="script" if collect_type == "script" else "builtin",
    )
    plugin.monitor_object.add(obj)
    return plugin


def _instance(obj, instance_id, **kwargs):
    return MonitorInstance.objects.create(
        id=instance_id,
        name=kwargs.pop("name", instance_id),
        monitor_object=obj,
        **kwargs,
    )


def test_two_script_plugins_can_share_one_instance():
    obj = _object("MySQL")
    instance = _instance(obj, "('mysql-1',)", name="orders", ip="10.1.2.3")
    first = _plugin("script-a", obj)
    second = _plugin("script-b", obj)
    CollectConfig.objects.create(
        id="cfg-a",
        monitor_instance=instance,
        monitor_plugin=first,
        collector="Telegraf",
        collect_type="script",
        config_type="script",
        file_type="toml",
        is_child=True,
    )
    CollectConfig.objects.create(
        id="cfg-b",
        monitor_instance=instance,
        monitor_plugin=second,
        collector="Telegraf",
        collect_type="script",
        config_type="script",
        file_type="toml",
        is_child=True,
    )

    controller = Controller({"monitor_plugin_id": second.id, "collect_type": "script"})
    found = controller._lookup_existing_script_collect_configs(
        [{"instance_id": instance.id, "type": "script"}],
        "script",
        second.id,
    )
    assert found[(instance.id, "script", True)].id == "cfg-b"
    missed = controller._lookup_existing_script_collect_configs(
        [{"instance_id": instance.id, "type": "script"}],
        "script",
        first.id,
    )
    assert missed[(instance.id, "script", True)].id == "cfg-a"
    assert len(CollectConfig.objects.filter(monitor_instance=instance, collect_type="script")) == 2


def test_script_attach_keeps_switch_storage_key(monkeypatch):
    obj = _object("Switch")
    instance = _instance(obj, "('sw-1',)", name="core-sw", is_active=True)
    plugin = _plugin("switch-script", obj)
    captured = {}

    def fake_controller(self):
        captured["instances"] = self.data["instances"]

    monkeypatch.setattr(Controller, "controller", fake_controller)
    monkeypatch.setattr(InstanceConfigService, "_validate_expected_collect_configs", staticmethod(lambda *args, **kwargs: None))
    result = InstanceConfigService.create_monitor_instance_by_node_mgmt(
        {
            "monitor_object_id": obj.id,
            "monitor_plugin_id": plugin.id,
            "collect_type": "script",
            "collector": "Telegraf",
            "instances": [
                {
                    "instance_id": instance.id,
                    "instance_name": instance.name,
                    "node_ids": ["node-1"],
                    "interval": 60,
                }
            ],
            "configs": [{"type": "script", "interval": 60}],
        }
    )

    assert result
    assert captured["instances"][0]["instance_id"] == "('sw-1',)"
    assert captured["instances"][0]["logical_instance_value"] == "sw-1"
    assert MonitorInstance.objects.filter(id="('sw-1',)").exists()


def test_bind_records_logical_identity():
    instances = [{"instance_id": "('db-9',)"}]
    bind_script_attach_instance_keys(instances)
    assert instances[0]["storage_instance_key"] == "('db-9',)"
    assert instances[0]["logical_instance_value"] == "db-9"


def test_native_plugin_filter_stays_on_reporting_points():
    obj = _object("Redis")
    exporter = _plugin("redis-exporter", obj, collect_type="exporter")
    script = _plugin("redis-script", obj)
    assert plugin_filter_membership(obj, exporter) is None
    assert plugin_filter_membership(obj, script) == set()


def _child_config(instance, config_id):
    CollectConfig.objects.create(
        id=config_id,
        monitor_instance=instance,
        collector="Telegraf",
        collect_type="exporter",
        config_type="postgres",
        file_type="toml",
        is_child=True,
    )


def test_script_candidate_prefills_the_single_active_node(monkeypatch):
    obj = _object("Postgres")
    instance = _instance(obj, "('pg-1',)", name="pg-1")
    _child_config(instance, "pg-child")
    seen = {}

    class FakeNodeMgmt:
        def get_child_config_nodes_by_ids(self, ids, organization_ids):
            seen["ids"] = list(ids)
            seen["organization_ids"] = list(organization_ids)
            return [{"id": "pg-child", "nodes": [{"id": "pg-node", "name": "采集机", "active": True}]}]

    monkeypatch.setattr("apps.rpc.node_mgmt.NodeMgmt", FakeNodeMgmt)
    items = [{"instance_id": instance.id, "node_id": ""}]
    fill_script_attach_collector_nodes(items, [7])
    assert seen["organization_ids"] == [7]
    assert "pg-child" in seen["ids"]
    assert items[0]["node_id"] == "pg-node"
    assert items[0]["node_name"] == "采集机"


def test_script_candidate_does_not_guess_among_nodes(monkeypatch):
    obj = _object("PostgresTwo")
    instance = _instance(obj, "('pg-2',)", name="pg-2")
    _child_config(instance, "pg-child-2")

    class FakeNodeMgmt:
        def get_child_config_nodes_by_ids(self, ids, organization_ids):
            return [
                {
                    "id": "pg-child-2",
                    "nodes": [
                        {"id": "pg-node-a", "name": "甲", "active": True},
                        {"id": "pg-node-b", "name": "乙", "active": True},
                    ],
                }
            ]

    monkeypatch.setattr("apps.rpc.node_mgmt.NodeMgmt", FakeNodeMgmt)
    items = [{"instance_id": instance.id, "node_id": ""}]
    fill_script_attach_collector_nodes(items, [7])
    assert items[0]["node_id"] == ""
    assert "node_name" not in items[0]


def test_existing_node_keeps_its_id_and_gains_a_name(monkeypatch):
    obj = _object("HostLike")
    instance = _instance(obj, "('host-1',)", name="host-1", node_id="host-node")
    _child_config(instance, "host-child")

    class FakeNodeMgmt:
        def get_child_config_nodes_by_ids(self, ids, organization_ids):
            return [{"id": "host-child", "nodes": [{"id": "host-node", "name": "主机采集机", "active": True}]}]

    monkeypatch.setattr("apps.rpc.node_mgmt.NodeMgmt", FakeNodeMgmt)
    items = [{"instance_id": instance.id, "node_id": instance.node_id}]
    fill_script_attach_collector_nodes(items, [7])
    assert items[0]["node_id"] == "host-node"
    assert items[0]["node_name"] == "主机采集机"


# ---------- 端到端：真实下发器 + 列表 + 卸载 + 告警圈选 + 展示指标 ----------


class _FakeNodeMgmt:
    created: list = []
    updated: list = []
    deleted: list = []

    def __init__(self, *args, **kwargs):
        pass

    def batch_create_configs_and_child_configs(self, configs, child_configs):
        _FakeNodeMgmt.created.extend(child_configs)

    def update_child_config_content(self, config_id, content, env_config=None):
        _FakeNodeMgmt.updated.append((config_id, content))

    def update_config_content(self, config_id, content, env_config=None):
        _FakeNodeMgmt.updated.append((config_id, content))

    def delete_child_configs(self, ids):
        _FakeNodeMgmt.deleted.extend(ids)

    def delete_configs(self, ids):
        _FakeNodeMgmt.deleted.extend(ids)

    def get_nodes_by_ids(self, ids):
        return []

    def get_child_config_nodes_by_ids(self, ids, organization_ids):
        return []


@pytest.fixture
def attach_env(monkeypatch):
    from apps.monitor.services.custom_script_plugin import CustomScriptPluginService
    from apps.monitor.utils.victoriametrics_api import VictoriaMetricsAPI

    _FakeNodeMgmt.created, _FakeNodeMgmt.updated, _FakeNodeMgmt.deleted = [], [], []
    for target in (
        "apps.monitor.utils.plugin_controller.NodeMgmt",
        "apps.monitor.services.node_mgmt.NodeMgmt",
        "apps.monitor.services.monitor_plugin_unbind.NodeMgmt",
        "apps.rpc.node_mgmt.NodeMgmt",
    ):
        monkeypatch.setattr(target, _FakeNodeMgmt)
    vm_queries = []

    def fake_query(self, query, *args, **kwargs):
        vm_queries.append(query)
        return {"data": {"result": []}}

    monkeypatch.setattr(VictoriaMetricsAPI, "query", fake_query)

    obj = MonitorObject.objects.create(
        name="MySQL",
        level="base",
        instance_id_keys=["instance_id"],
        default_metric="any({instance_type='mysql'}) by (instance_id)",
    )
    native = MonitorPlugin.objects.create(
        name="mysql-native",
        collect_type="database",
        collector="Telegraf",
        template_id="mysql-native",
        status_query="any({instance_type='mysql', collect_type='database'}) by (instance_id)",
    )
    native.monitor_object.add(obj)
    scripts = []
    for name in ("script-a", "script-b"):
        plugin = MonitorPlugin.objects.create(
            name=name,
            display_name=name,
            collect_type="script",
            collector="Telegraf",
            template_id=name,
            template_type="script",
            is_pre=False,
            status_query=f"any({{plugin_id='{name}'}}) by (instance_id)",
        )
        plugin.monitor_object.add(obj)
        CustomScriptPluginService.initialize_templates(plugin)
        scripts.append(plugin)
    instance = MonitorInstance.objects.create(id="('mysql-1',)", name="orders-db", monitor_object=obj, interval=30)
    CollectConfig.objects.create(
        id="native-cfg",
        monitor_instance=instance,
        monitor_plugin=native,
        collector="Telegraf",
        collect_type="database",
        config_type="mysql",
        file_type="toml",
        is_child=True,
    )
    return {"obj": obj, "native": native, "a": scripts[0], "b": scripts[1], "instance": instance, "vm_queries": vm_queries}


def _attach(env, plugin, script="echo 'conn 1'"):
    return InstanceConfigService.create_monitor_instance_by_node_mgmt(
        {
            "monitor_object_id": env["obj"].id,
            "monitor_plugin_id": plugin.id,
            "collect_type": "script",
            "collector": "Telegraf",
            "instances": [
                {
                    "instance_id": env["instance"].id,
                    "instance_name": "should-not-rename",
                    "node_ids": ["node-1"],
                    "interval": 60,
                    "instance_type": env["obj"].name,
                    "group_ids": [99],
                }
            ],
            "configs": [{"type": "script", "interval": 60, "script": script, "interpreter": "/bin/sh", "script_os": "linux"}],
        }
    )


def test_two_scripts_attach_through_the_real_controller(attach_env):
    env = attach_env
    instance = env["instance"]
    _attach(env, env["a"])
    _attach(env, env["b"], script="echo 'slow 2'")

    rows = {row.monitor_plugin_id: row for row in CollectConfig.objects.filter(monitor_instance=instance, collect_type="script")}
    assert set(rows) == {env["a"].id, env["b"].id}
    assert MonitorInstance.objects.filter(monitor_object=env["obj"]).count() == 1
    instance.refresh_from_db()
    assert (instance.name, instance.interval) == ("orders-db", 30)
    assert not instance.monitorinstanceorganization_set.exists()

    rendered = {item["id"]: item["content"] for item in _FakeNodeMgmt.created}
    toml_a = rendered[rows[env["a"].id].id]
    toml_b = rendered[rows[env["b"].id].id]
    assert 'instance_id = "mysql-1"' in toml_a and 'instance_id = "mysql-1"' in toml_b
    assert 'plugin_id = "script-a"' in toml_a and 'plugin_id = "script-b"' in toml_b
    assert 'collect_type = "script"' in toml_a
    assert 'instance_type = "MySQL"' in toml_a

    # 同一插件再提交一次是更新，不新增，也不动另一份脚本。
    _attach(env, env["a"], script="echo 'conn 3'")
    assert CollectConfig.objects.filter(monitor_instance=instance, collect_type="script").count() == 2
    assert [config_id for config_id, _ in _FakeNodeMgmt.updated] == [rows[env["a"].id].id]
    assert CollectConfig.objects.get(id=rows[env["b"].id].id).monitor_plugin_id == env["b"].id
    assert CollectConfig.objects.get(id="native-cfg").monitor_plugin_id == env["native"].id


def test_lists_views_and_unbind_after_attach(attach_env):
    from apps.monitor.services.effective_plugins import MonitorEffectivePluginService
    from apps.monitor.services.monitor_object import MonitorObjectService
    from apps.monitor.services.monitor_plugin_unbind import MonitorPluginUnbindService

    env = attach_env
    instance = env["instance"]
    _attach(env, env["a"])

    def listed(plugin):
        data = MonitorObjectService.get_monitor_instance(env["obj"].id, 1, 10, None, MonitorInstance.objects.all(), monitor_plugin_id=plugin.id)
        return [item["instance_id"] for item in data["results"]]

    # 脚本 A 已挂上但还没出点：按 A 过滤能看到；B 没挂：看不到；原生没有上报点：沿用原行为不列出。
    assert listed(env["a"]) == [instance.id]
    assert listed(env["b"]) == []
    assert listed(env["native"]) == []
    # 对象默认列表不受影响。
    assert [
        item["instance_id"]
        for item in MonitorObjectService.get_monitor_instance(env["obj"].id, 1, 10, None, MonitorInstance.objects.all())["results"]
    ] == [instance.id]
    # 原生状态查询不取脚本序列；脚本状态只看本模板。
    joined = "\n".join(env["vm_queries"])
    assert "unless" not in joined
    assert "{instance_type='mysql', collect_type!=\"script\"}" in joined
    assert 'collect_type="script", plugin_id="script-a"' in joined

    effective = {item["id"]: item for item in MonitorEffectivePluginService.get_effective_plugins(env["obj"].id, instance.id)}
    assert set(effective) == {env["native"].id, env["a"].id}
    assert effective[env["a"].id]["configured"] is True

    MonitorPluginUnbindService.unbind(instance.id, env["a"].id)
    assert not CollectConfig.objects.filter(monitor_instance=instance, collect_type="script").exists()
    assert CollectConfig.objects.filter(id="native-cfg").exists()
    assert MonitorInstance.objects.filter(id=instance.id, is_deleted=False).exists()
    assert listed(env["a"]) == []


def test_script_policy_scans_only_instances_with_that_script(attach_env):
    from types import SimpleNamespace

    from apps.monitor.models import Metric
    from apps.monitor.services.script_attach import restrict_script_policy_instances

    env = attach_env
    other = MonitorInstance.objects.create(id="('mysql-2',)", name="billing-db", monitor_object=env["obj"])
    _attach(env, env["a"])
    metric_a = Metric.objects.filter(monitor_plugin=env["a"]).first()
    native_metric = Metric.objects.create(
        monitor_object=env["obj"],
        monitor_plugin=env["native"],
        metric_group=metric_a.metric_group,
        name="mysql_up",
        query="mysql_up{instance_type='mysql', __$labels__}",
    )
    scope = {env["instance"].id: "orders-db", other.id: "billing-db"}

    script_policy = SimpleNamespace(id=1, collect_type="script", source_template=None, query_condition={"type": "metric", "metric_id": metric_a.id})
    kept, _ = restrict_script_policy_instances(script_policy, dict(scope), {})
    assert set(kept) == {env["instance"].id}

    native_policy = SimpleNamespace(
        id=2, collect_type="database", source_template=None, query_condition={"type": "metric", "metric_id": native_metric.id}
    )
    kept, _ = restrict_script_policy_instances(native_policy, dict(scope), {})
    assert set(kept) == set(scope)


def test_same_named_script_metric_does_not_take_over_native_columns(attach_env, monkeypatch):
    from apps.monitor.models import Metric
    from apps.monitor.services.monitor_object import MonitorObjectService

    env = attach_env
    _attach(env, env["a"])
    group = Metric.objects.filter(monitor_plugin=env["a"]).first().metric_group
    # 先建脚本指标，让它排在前面。
    Metric.objects.create(monitor_object=env["obj"], monitor_plugin=env["a"], metric_group=group, name="conn", query="conn{__$labels__}")
    Metric.objects.create(
        monitor_object=env["obj"], monitor_plugin=env["native"], metric_group=group, name="conn", query="conn{instance_type='mysql', __$labels__}"
    )
    picked = []

    def fake_values(metric_obj, target_instances):
        picked.append(metric_obj.monitor_plugin.name)
        return {}

    monkeypatch.setattr(MonitorObjectService, "_query_metric_values", staticmethod(fake_values))
    rows = [{"instance_id": env["instance"].id}]

    legacy = {"display_fields": [{"name": "连接数", "sort_order": 0, "metrics": [{"plugin": "", "metric": "conn"}]}]}
    MonitorObjectService._fill_display_metrics(env["obj"].id, legacy, rows)
    assert picked == ["mysql-native"]

    picked.clear()
    MonitorObjectService._fill_display_metrics(env["obj"].id, {"display_fields": [], "supplementary_indicators": ["conn"]}, rows)
    assert picked == ["mysql-native"]

    picked.clear()
    bound = {"display_fields": [{"name": "脚本连接数", "sort_order": 0, "metrics": [{"plugin": "script-a", "metric": "conn"}]}]}
    MonitorObjectService._fill_display_metrics(env["obj"].id, bound, rows)
    assert picked == ["script-a"]


def test_collection_status_keeps_native_and_script_apart(attach_env):
    from apps.monitor.services.collection_query import _report_maps

    env = attach_env
    instance = MonitorInstance.objects.select_related("monitor_object").get(id=env["instance"].id)
    seen = []

    class FakeVm:
        def query(self, promql, step=None, **kwargs):
            seen.append(promql)
            return {"data": {"result": []}}

    _report_maps(
        [instance],
        {env["obj"].id: [env["native"], env["a"]]},
        FakeVm(),
        {instance.id: {env["native"].id, env["a"].id}},
        None,
    )
    native_query = next(item for item in seen if "instance_type='mysql'" in item)
    script_query = next(item for item in seen if "plugin_id='script-a'" in item)
    assert "collect_type='database'" in native_query and "unless" not in native_query
    assert 'collect_type!="script"' not in script_query

    seen.clear()
    env["native"].status_query = "any({instance_type='mysql'}) by (instance_id)"
    _report_maps([instance], {env["obj"].id: [env["native"]]}, FakeVm(), {instance.id: {env["native"].id}}, None)
    assert any('collect_type!="script"' in item and "instance_type='mysql'" in item for item in seen)
