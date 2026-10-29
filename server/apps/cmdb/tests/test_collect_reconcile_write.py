"""调和落库走 MetricsCannula → Management，图用假客户端。"""

from apps.cmdb.collection.common import Management
from apps.cmdb.collection.metrics_cannula import MetricsCannula


class FakeGraph:
    def __init__(self, rows):
        self.rows = [dict(row) for row in rows]
        self.writes = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def query_entity(self, label, conds):
        names = None
        task_id = None
        for cond in conds:
            if cond["field"] == "inst_name":
                names = set(cond["value"])
            if cond["field"] == "collect_task":
                task_id = str(cond["value"])
        matched = []
        for row in self.rows:
            if names is not None and row.get("inst_name") not in names:
                continue
            if task_id is not None and str(row.get("collect_task")) != task_id:
                continue
            matched.append(dict(row))
        return matched, len(matched)

    def set_entity_properties(self, label, ids, info, check_attr_map, exist_items):
        saved = dict(info)
        saved["_id"] = ids[0]
        self.writes.append(saved)
        return [saved]

    def create_entity(self, label, info, check_attr_map, exist_items):
        saved = dict(info)
        saved["_id"] = 100 + len(self.rows)
        self.rows.append(saved)
        self.writes.append(saved)
        return saved

    def delete_entity_if_unchanged(self, label, instance):
        return False


def _patch(monkeypatch, graph):
    monkeypatch.setattr("apps.cmdb.collection.common.GraphClient", lambda *a, **k: graph)
    monkeypatch.setattr("apps.cmdb.collection.metrics_cannula.GraphClient", lambda *a, **k: graph)
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_attr", lambda model_id: [{"attr_id": "port", "attr_name": "端口", "editable": True}]
    )
    monkeypatch.setattr("apps.cmdb.collection.common.write_collect_instance_change_records", lambda *a, **k: None)

    class _Ext:
        def on_collect_instances_applied(self, **kwargs):
            return None

    monkeypatch.setattr("apps.cmdb.collection.common.get_collect_enterprise_extension", lambda: _Ext())
    import apps.cmdb.services.auto_relation_reconcile as auto

    monkeypatch.setattr(auto, "schedule_instance_auto_relation_reconcile", lambda ids: None)
    monkeypatch.setattr(auto, "schedule_incoming_rule_full_sync_by_model_ids", lambda ids: None)


def test_snmp_device_is_written_by_model_field_and_read_back(monkeypatch):
    graph = FakeGraph([])
    _patch(monkeypatch, graph)
    monkeypatch.setattr(
        "apps.cmdb.services.model.ModelManage.search_model_attr",
        lambda model_id: [
            {"attr_id": "ip_addr", "attr_name": "IP", "editable": True},
            {"attr_id": "sys_desc", "attr_name": "系统描述", "editable": True},
            {"attr_id": "soid", "attr_name": "对象标识", "editable": True},
        ],
    )
    monkeypatch.setattr("apps.cmdb.services.collect_reconcile.load_write_context", lambda task_id: None)

    class Task:
        model_id = "network"
        expire_days = 0
        instances = []

    from apps.cmdb.collection.plugins.community.network.plugins import NETWORK_DEVICE_MAPPING

    raw = {
        "ip_addr": "10.10.69.247",
        "sysdescr": "S5735S-L8T4S-QA2",
        "sysobjectid": "1.3.6.1.4.1.2011.2.23.968",
    }
    converted = {"inst_name": raw["ip_addr"]}
    for field, source in NETWORK_DEVICE_MAPPING.items():
        if isinstance(source, str):
            converted[field] = raw.get(source, "")
    cannula = MetricsCannula(
        inst_id=1,
        organization=[1],
        inst_name="snmp",
        task_id=31,
        collect_plugin=object,
        default_metrics={"network": [converted]},
        reconcile_task_assets=True,
        task=Task(),
    )
    cannula.collect_controller()
    found, count = graph.query_entity("network", [{"field": "inst_name", "type": "str=", "value": ["10.10.69.247"]}])
    assert count == 1
    assert found[0]["sys_desc"] == "S5735S-L8T4S-QA2"
    assert found[0]["soid"] == "1.3.6.1.4.1.2011.2.23.968"
    assert "sysdescr" not in found[0]


def test_network_reconcile_keeps_switch_field_when_custom_is_lower(monkeypatch):
    graph = FakeGraph(
        [
            {
                "_id": 1,
                "model_id": "switch",
                "inst_name": "10.10.69.245-switch",
                "collect_task": "14",
                "organization": [1],
                "sys_desc": "H3C Switch S2610V2",
                "collect_time": "2026-10-28T00:00:00+00:00",
                "_collect_sources": (
                    '{"fields":{"sys_desc":{"source":"14","updated_at":"2026-10-28T00:00:00+00:00"}},' '"seen":{"14":"2026-10-28T00:00:00+00:00"}}'
                ),
            }
        ]
    )
    _patch(monkeypatch, graph)
    monkeypatch.setattr(
        "apps.cmdb.services.collect_reconcile.load_write_context",
        lambda task_id: {
            "model_id": "network",
            "member_order": ["14", "15"],
            "field_orders": {"sys_desc": ["14", "15"]},
            "stale_days": 7,
        },
    )

    class Task:
        model_id = "network"
        expire_days = 0
        instances = []

    cannula = MetricsCannula(
        inst_id=15,
        organization=[1],
        inst_name="custom",
        task_id=15,
        collect_plugin=object,
        default_metrics={"switch": [{"inst_name": "10.10.69.245-switch", "sys_desc": "custom:H3C Switch S2610V2"}]},
        reconcile_task_assets=True,
        task=Task(),
    )
    result = cannula.collect_controller()
    assert result["switch"]["update"]["failed"] == []
    assert all("custom:" not in str(item.get("sys_desc", "")) for item in graph.writes)
    found, _count = graph.query_entity("switch", [{"field": "inst_name", "type": "str=", "value": ["10.10.69.245-switch"]}])
    assert found[0]["sys_desc"] == "H3C Switch S2610V2"
    assert found[0]["collect_task"] == "14"


def test_second_task_fills_fields_without_conflict_and_outsider_still_conflicts(monkeypatch):
    graph = FakeGraph(
        [
            {
                "_id": 1,
                "model_id": "mysql",
                "inst_name": "ip1",
                "collect_task": "11",
                "organization": [1],
                "port": "3306",
                "collect_time": "2026-10-26T00:00:00+00:00",
            }
        ]
    )
    _patch(monkeypatch, graph)
    context = {"model_id": "mysql", "member_order": ["11", "12"], "field_orders": {"port": ["11", "12"], "version": ["12"]}, "stale_days": 7}
    monkeypatch.setattr(
        "apps.cmdb.services.collect_reconcile.load_write_context", lambda task_id: context if str(task_id) in {"11", "12", "13"} else None
    )

    class Task:
        model_id = "mysql"
        expire_days = 0
        instances = []

    cannula = MetricsCannula(
        inst_id=1,
        organization=[1],
        inst_name="task",
        task_id=12,
        collect_plugin=object,
        default_metrics={"mysql": [{"inst_name": "ip1", "version": "8.0"}]},
        reconcile_task_assets=True,
        task=Task(),
    )
    result = cannula.collect_controller()
    assert result["mysql"]["update"]["failed"] == []
    assert result["mysql"]["reconcile_stats"]["skipped_fields"] == 0
    written = graph.writes[-1]
    assert written["version"] == "8.0"
    assert written["collect_task"] == "11"

    outsider = MetricsCannula(
        inst_id=1,
        organization=[1],
        inst_name="task",
        task_id=13,
        collect_plugin=object,
        default_metrics={"mysql": [{"inst_name": "ip1", "port": "3307"}]},
        reconcile_task_assets=True,
        task=Task(),
    )
    monkeypatch.setattr("apps.cmdb.services.collect_reconcile.load_write_context", lambda task_id: None)
    outsider_result = outsider.collect_controller()
    assert outsider_result["mysql"]["update"]["failed"]
    assert "其他采集任务" in outsider_result["mysql"]["update"]["failed"][0]["error"]


def test_child_model_still_conflicts_when_main_instance_reconciles(monkeypatch):
    graph = FakeGraph(
        [
            {"_id": 1, "model_id": "network", "inst_name": "sw1", "collect_task": "21", "organization": [1]},
            {"_id": 2, "model_id": "interface", "inst_name": "eth0", "collect_task": "21", "organization": [1]},
        ]
    )
    _patch(monkeypatch, graph)
    monkeypatch.setattr(
        "apps.cmdb.services.collect_reconcile.load_write_context",
        lambda task_id: {"model_id": "network", "member_order": ["21", "22"], "field_orders": {}, "stale_days": 7},
    )

    class Task:
        model_id = "network"
        expire_days = 0
        instances = []

    cannula = MetricsCannula(
        inst_id=1,
        organization=[1],
        inst_name="snmp",
        task_id=22,
        collect_plugin=object,
        default_metrics={"network": [{"inst_name": "sw1", "ip_addr": "10.0.0.1"}], "interface": [{"inst_name": "eth0"}]},
        reconcile_task_assets=True,
        task=Task(),
    )
    result = cannula.collect_controller()
    assert result["network"]["update"]["failed"] == []
    assert result["interface"]["update"]["failed"]
    assert "其他采集任务" in result["interface"]["update"]["failed"][0]["error"]


def test_format_collect_data_keeps_reconcile_stats_out_of_instance_rows():
    from apps.cmdb.collection.collect_tasks.base import BaseCollect

    collector = object.__new__(BaseCollect)
    formatted = BaseCollect.format_collect_data(
        collector,
        {
            "mysql": {
                "add": {"success": [], "failed": []},
                "update": {"success": [{"inst_info": {"inst_name": "ip1", "model_id": "mysql"}}], "failed": []},
                "delete": {"success": [], "failed": []},
                "reconcile_stats": {
                    "skipped_fields": 2,
                    "org_conflicts": 1,
                    "outside_owner_conflicts": 0,
                    "concurrent_abandons": 0,
                },
            },
            "all": 1,
        },
    )
    assert formatted["reconcile_stats"]["skipped_fields"] == 2
    assert formatted["reconcile_stats"]["org_conflicts"] == 1
    assert formatted["update"][0]["inst_name"] == "ip1"


def test_management_keeps_runtime_inst_name(monkeypatch):
    _patch(monkeypatch, FakeGraph([]))
    management = Management(
        organization=[1],
        inst_name="task",
        model_id="mysql",
        old_data=[{"_id": 1, "inst_name": "ip1", "collect_task": "11", "organization": [1], "port": "3306"}],
        new_data=[{"inst_name": "ip1", "port": "3307"}],
        unique_keys=["inst_name"],
        collect_time="2026-10-27T00:00:00+00:00",
        task_id="12",
        reconcile={"member_order": ["11", "12"], "field_orders": {"port": ["12", "11"]}, "stale_days": 7},
    )
    assert management.update_list[0]["inst_name"] == "ip1"
    assert management.update_list[0]["port"] == "3307"
    assert "collect_task" in management.check_attr_map["editable"]
    assert "_collect_sources" in management.check_attr_map["editable"]
