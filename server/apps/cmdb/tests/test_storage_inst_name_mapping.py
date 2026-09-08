# -*- coding: utf-8 -*-
"""主对象 storage 必须带 inst_name：映射契约 + format_metrics 产出 + 缺映射兜底。

日本节点曾热补 CollectionPlugin.field_mappings 未生效（registry / 双导入路径）。
本用例锁：
- 导入类与 registry 解析类的 storage 映射都含 inst_name；
- format_metrics 产出的 storage 行 inst_name 等于采集器 inst_name；
- 即使映射被剥掉 inst_name，主对象仍回填 self.inst_name。
"""
import time

from apps.cmdb.collection.plugins.registry import CollectionPluginRegistry
from apps.cmdb.constants.constants import CollectPluginTypes

STORAGE_CASES = (
    ("storage", "apps.cmdb.collection.collect_plugin.oceanstor", "OceanStorCollectMetrics", "华为存储-inst-name"),
    ("netapp_ontap", "apps.cmdb.collection.collect_plugin.netapp_ontap", "NetAppOntapCollectMetrics", "NetApp-inst-name"),
    ("dell_unity", "apps.cmdb.collection.collect_plugin.dell_unity", "DellUnityCollectMetrics", "Unity-inst-name"),
)


def _plugin_cls(model_id):
    return CollectionPluginRegistry.get_plugin(CollectPluginTypes.CLOUD, model_id)


def _import_plugin_cls(model_id):
    if model_id == "storage":
        from apps.cmdb.collection.plugins.community.cloud.oceanstor import OceanStorCollectionPlugin

        return OceanStorCollectionPlugin
    if model_id == "netapp_ontap":
        from apps.cmdb.collection.plugins.community.cloud.netapp_ontap import NetAppOntapCollectionPlugin

        return NetAppOntapCollectionPlugin
    from apps.cmdb.collection.plugins.community.cloud.dell_unity import DellUnityCollectionPlugin

    return DellUnityCollectionPlugin


def _make_runner(monkeypatch, model_id, inst_name, plugin_cls=None):
    import importlib

    _, metrics_mod, metrics_name, _ = next(item for item in STORAGE_CASES if item[0] == model_id)
    metrics_cls = getattr(importlib.import_module(metrics_mod), metrics_name)
    plugin_cls = plugin_cls or _plugin_cls(model_id)

    class _FakeInst:
        def __init__(self):
            self.model_id = model_id
            self.instances = [{"inst_name": inst_name}]

    monkeypatch.setattr(metrics_cls, "get_collect_inst", lambda self: _FakeInst())
    return plugin_cls(inst_name=inst_name, inst_id=1, task_id=9901)


def _storage_only_vector():
    ts = int(time.time()) - 60
    return {
        "result": [
            {
                "metric": {
                    "__name__": "storage_info_gauge",
                    "collect_status": "success",
                    "device_sn": "SN-INST-NAME",
                    "ip_addr": "10.0.0.1",
                    "model": "dummy",
                    "brand": "dummy",
                    "storage_type": "SAN",
                    "firmware_version": "1",
                    "sys_desc": "dummy",
                    "total_capacity": "1",
                    "used_capacity": "0",
                    "available_capacity": "1",
                    "pool_count": "0",
                    "disk_count": "0",
                    "volume_count": "0",
                    "state": "online",
                    "RUNNINGSTATUS": "27",
                },
                "value": [ts, "1"],
            }
        ]
    }


def test_storage_field_mappings_require_inst_name_on_import_and_registry():
    for model_id, *_rest in STORAGE_CASES:
        imported = _import_plugin_cls(model_id)
        registered = _plugin_cls(model_id)
        assert "inst_name" in imported.field_mappings["storage"], f"{imported.__name__} storage mapping 缺少 inst_name"
        assert "inst_name" in registered.field_mappings["storage"], f"registry {model_id} storage mapping 缺少 inst_name"
        assert registered is imported, f"registry[{model_id}] 不是导入类 {imported.__name__}，热补导入类不会生效"


def test_format_metrics_storage_rows_use_collector_inst_name(monkeypatch):
    for model_id, _mod, _name, inst_name in STORAGE_CASES:
        plugin_cls = _plugin_cls(model_id)
        assert "inst_name" in plugin_cls.field_mappings["storage"]
        runner = _make_runner(monkeypatch, model_id, inst_name, plugin_cls=plugin_cls)
        runner.format_data(_storage_only_vector())
        runner.format_metrics()
        storage = runner.result["storage"]
        assert storage, f"{model_id} format_metrics 未产出 storage"
        assert storage[0]["inst_name"] == inst_name == runner.inst_name


def test_format_metrics_backfills_storage_inst_name_when_mapping_omits_it(monkeypatch):
    for model_id, _mod, _name, inst_name in STORAGE_CASES:
        plugin_cls = _plugin_cls(model_id)
        stripped = {key: dict(mapping) for key, mapping in plugin_cls.field_mappings.items()}
        stripped["storage"].pop("inst_name", None)
        monkeypatch.setattr(plugin_cls, "field_mappings", stripped)
        runner = _make_runner(monkeypatch, model_id, inst_name, plugin_cls=plugin_cls)
        runner.format_data(_storage_only_vector())
        runner.format_metrics()
        assert runner.result["storage"][0]["inst_name"] == inst_name
