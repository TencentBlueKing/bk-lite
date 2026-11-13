"""三种清理策略跨插件的行为回归：真实对账，仅替换外部存储。"""
import copy
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from apps.cmdb.collection.collect_tasks.base import BaseCollect
from apps.cmdb.collection.metrics_cannula import MetricsCannula
from apps.cmdb.collection.plugins import get_collection_plugin
from apps.cmdb.collection.plugins.registry import CollectionPluginRegistry
from apps.cmdb.tests.test_vmware_collection_ownership_service import graph as vmware_graph


@pytest.fixture
def graph(monkeypatch):
    graph = vmware_graph.__wrapped__(monkeypatch)
    monkeypatch.setattr("apps.cmdb.services.collect_reconcile.load_write_context", lambda task_id: None)
    return graph


NOW = "2026-08-29T04:00:00+00:00"
OLD = "2026-08-24T04:00:00+00:00"
BOUNDARY = "2026-08-26T04:00:00+00:00"
FAMILIES = [
    ("cloud", "aliyun_account", "aliyun_ecs"),
    ("cloud", "hwcloud", "hwcloud_ecs"),
    ("k8s", "k8s_cluster", "k8s_pod"),
    ("cloud", "h3c_cas", "h3c_cas_vm"),
    ("cloud", "winsphere", "winsphere_vm"),
]


def reconcile(graph, family, strategy, complete=True, rows=None, targets=()):
    kind, root, child = family
    task = SimpleNamespace(id=42, model_id=root, expire_days=3, instances=list(targets), data_cleanup_strategy=strategy)
    cls = get_collection_plugin(kind, root)
    plugin = cls("platform", None, "42", collect_inst=task, snapshot_complete=complete)
    if hasattr(plugin, "is_authoritative_snapshot"):
        plugin._authoritative_models = {child: complete is True}
    cannula = MetricsCannula(
        None, [1], "platform", 42, cls, default_metrics={child: rows or []}, task=task, reconcile_task_assets=True, data_cleanup_strategy=strategy
    )
    cannula.collect_plugin_instance = plugin
    cannula.now_time = NOW
    result = cannula.collect_controller()
    return BaseCollect.__new__(BaseCollect).format_collect_data(result)


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("strategy,expected", [("no_cleanup", False), ("immediately", True), ("after_expiration", True)])
@pytest.mark.parametrize("owner", [42, "42"])
def test_complete_empty_snapshot_applies_all_three_strategies(graph, family, strategy, expected, owner):
    old = graph.insert("gone", family[2], owner=owner, collect_time=OLD)
    result = reconcile(graph, family, strategy)
    assert (old["_id"] not in graph.rows) is expected
    assert len(result["delete"]) == int(expected)
    if expected:
        assert result["delete"][0]["inst_uuid"] == old["inst_uuid"]
        assert result["delete"][0]["_status"] == "success"


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("complete", [False, None])
@pytest.mark.parametrize("strategy", ["immediately", "after_expiration"])
def test_unknown_or_partial_snapshot_never_deletes_even_with_nonempty_results(graph, family, complete, strategy):
    old = graph.insert("gone", family[2], owner="42", collect_time=OLD)
    reconcile(graph, family, strategy, complete, rows=[{"inst_name": "present"}])
    assert graph.rows[old["_id"]] == old


@pytest.mark.parametrize("family", FAMILIES)
def test_expiration_preserves_recent_boundary_foreign_unowned_and_selected_targets(graph, family):
    rows = [
        graph.insert(name, family[2], owner=owner, collect_time=ctime)
        for name, owner, ctime in [
            ("recent", "42", NOW),
            ("boundary", 42, BOUNDARY),
            ("foreign", "99", OLD),
            ("unowned", "", OLD),
            ("target", "42", OLD),
        ]
    ]
    result = reconcile(graph, family, "after_expiration", targets=[rows[-1]])
    assert all(graph.rows[r["_id"]] == r for r in rows)
    assert result["delete"] == []


def test_legacy_invalid_timestamp_does_not_block_other_candidates(graph):
    stale = graph.insert("gone", "aliyun_ecs", owner="42", collect_time=OLD)
    invalid = graph.insert("unknown-zone", "aliyun_ecs", owner="42", collect_time="2026-08-24 12:00:01")
    reconcile(graph, FAMILIES[0], "after_expiration")
    assert stale["_id"] not in graph.rows
    assert graph.rows[invalid["_id"]] == invalid


class _ProjectingGraph:
    """按查询字段投影，并执行 FalkorDB 的 _collect_sources 条件删除。"""

    def __init__(self):
        self.rows = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def insert(self, name, model="host", owner="", **extra):
        row = {
            "_id": len(self.rows) + 1,
            "inst_uuid": str(uuid4()),
            "model_id": model,
            "inst_name": name,
            "collect_task": owner,
            "organization": [1],
        }
        row.update(extra)
        self.rows[row["_id"]] = row
        return copy.deepcopy(row)

    def query_entity(self, label, params, page=None, fields=None, **kwargs):
        rows = list(self.rows.values())
        for param in params:
            field, value, kind = param["field"], param["value"], param["type"]
            if kind == "id>":
                rows = [row for row in rows if row.get("_id", 0) > value]
            else:
                rows = [row for row in rows if row.get(field) == value]
        rows.sort(key=lambda row: row["_id"])
        if page:
            rows = rows[: page["limit"]]
        if fields is not None:
            projected = []
            for row in rows:
                item = {"_id": row["_id"]}
                for field in fields:
                    if field != "_id" and field in row:
                        item[field] = row[field]
                projected.append(item)
            rows = projected
        return copy.deepcopy(rows), len(rows)

    def delete_entity_if_unchanged(self, label, instance):
        current = self.rows.get(instance.get("_id"))
        if current is None:
            return False
        for field in ("model_id", "inst_uuid", "collect_task", "collect_time"):
            if current.get(field) != instance.get(field):
                return False
        actual = current.get("_collect_sources")
        expected = instance.get("_collect_sources")
        if expected in (None, "") and actual not in (None, ""):
            return False
        if expected not in (None, "") and actual != expected:
            return False
        del self.rows[instance["_id"]]
        return True


def test_complete_snapshot_deletes_instance_with_collect_sources(monkeypatch):
    """有调和来源的实例必须能被完整快照删掉；投影漏掉 _collect_sources 时条件删除会失败。"""
    from apps.cmdb.collection import common, metrics_cannula

    graph = _ProjectingGraph()
    old = graph.insert(
        "gone",
        "aliyun_ecs",
        owner="42",
        collect_time=OLD,
        _collect_sources='{"seen":{"42":"2026-08-24T04:00:00+00:00"}}',
    )
    monkeypatch.setattr(common, "GraphClient", lambda **kwargs: graph)
    monkeypatch.setattr(metrics_cannula, "GraphClient", lambda **kwargs: graph)
    monkeypatch.setattr("apps.cmdb.services.collect_reconcile.load_write_context", lambda task_id: None)
    monkeypatch.setattr(common, "write_collect_instance_change_records", lambda *args, **kwargs: None)
    monkeypatch.setattr(common.ModelManage, "search_model_attr", lambda model: [])
    monkeypatch.setattr("apps.cmdb.services.auto_relation_reconcile.schedule_incoming_rule_full_sync_by_model_ids", lambda *args, **kwargs: None)
    reconcile(graph, FAMILIES[0], "immediately")
    assert old["_id"] not in graph.rows


def test_daily_cleanup_is_scheduled_at_02_00():
    from apps.cmdb.config import CELERY_BEAT_SCHEDULE
    from apps.core.celery_runtime.manifest import TASK_ROUTES

    entry = CELERY_BEAT_SCHEDULE["daily_data_cleanup"]
    assert entry["task"] == "apps.cmdb.tasks.celery_tasks.daily_data_cleanup_task"
    assert set(entry["schedule"].hour) == {2}
    assert set(entry["schedule"].minute) == {0}
    assert TASK_ROUTES[entry["task"]] == "background"


def _host_task(name, **fields):
    from apps.cmdb.models.collect_model import CollectModels

    values = dict(
        name=name,
        task_type="host",
        driver_type="protocol",
        model_id="host",
        cycle_value_type="hour",
        expire_days=3,
        data_cleanup_strategy="after_expiration",
        instances=[],
    )
    values.update(fields)
    return CollectModels.objects.create(**values)


@pytest.mark.django_db
def test_daily_cleanup_deletes_aged_owned_instances_without_waiting_for_collection(monkeypatch):
    from apps.cmdb.models.change_record import DELETE_INST, ChangeRecord
    from apps.cmdb.services.data_cleanup_service import DataCleanupService

    fixed_now = datetime(2026, 8, 29, 4, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("apps.cmdb.services.data_cleanup_service.timezone.now", lambda: fixed_now)
    task = _host_task("daily-expire")
    untouched = _host_task("daily-keep", data_cleanup_strategy="no_cleanup")
    graph = _ProjectingGraph()
    monkeypatch.setattr("apps.cmdb.services.data_cleanup_service.GraphClient", lambda **kwargs: graph)
    monkeypatch.setattr("apps.cmdb.services.model.ModelManage.search_model_attr", lambda model_id: [])
    aged_int = graph.insert("aged-int", owner=task.id, collect_time=OLD, _collect_sources='{"seen":{"1":"2026-08-24T04:00:00+00:00"}}')
    aged_str = graph.insert("aged-str", owner=str(task.id), collect_time=OLD)
    boundary = graph.insert("boundary", owner=task.id, collect_time=BOUNDARY)
    recent = graph.insert("recent", owner=str(task.id), collect_time=NOW)
    naive = graph.insert("naive", owner=task.id, collect_time="2026-08-24 12:00:01")
    foreign = graph.insert("foreign", owner=untouched.id, collect_time=OLD)
    target = graph.insert("target", owner=task.id, collect_time=OLD)
    task.instances = [{"inst_uuid": target["inst_uuid"], "model_id": "host", "inst_name": "target"}]
    task.save(update_fields=["instances"])

    summary = DataCleanupService.run_daily_cleanup()

    assert aged_int["_id"] not in graph.rows
    assert aged_str["_id"] not in graph.rows
    for kept in (boundary, recent, naive, foreign, target):
        assert graph.rows[kept["_id"]]["inst_name"] == kept["inst_name"]
    assert set(summary["delete_ids"]) >= {aged_int["_id"], aged_str["_id"]}
    deleted_ids = set(ChangeRecord.objects.filter(type=DELETE_INST).values_list("inst_id", flat=True))
    assert {aged_int["_id"], aged_str["_id"]} <= deleted_ids
    assert target["_id"] not in deleted_ids


@pytest.mark.django_db
def test_daily_cleanup_continues_after_one_task_fails_without_logging_payload(monkeypatch, caplog):
    from apps.cmdb.services.data_cleanup_service import DataCleanupService

    secret = "SENTINEL-cleanup-" + "payload"
    good = _host_task("daily-good")
    bad = _host_task("daily-bad")

    class _RaisingGraph(_ProjectingGraph):
        def query_entity(self, label, params, **kwargs):
            for param in params:
                if param["field"] == "collect_task" and str(param["value"]) == str(bad.id):
                    raise RuntimeError("token=" + secret)
            return super().query_entity(label, params, **kwargs)

    graph = _RaisingGraph()
    aged = graph.insert("aged", owner=good.id, collect_time=OLD)
    monkeypatch.setattr("apps.cmdb.services.data_cleanup_service.timezone.now", lambda: datetime(2026, 8, 29, 4, 0, tzinfo=timezone.utc))
    monkeypatch.setattr("apps.cmdb.services.data_cleanup_service.GraphClient", lambda **kwargs: graph)
    monkeypatch.setattr("apps.cmdb.services.data_cleanup_service._write_expiration_audit", lambda *args, **kwargs: None)
    monkeypatch.setattr("apps.cmdb.services.data_cleanup_service._schedule_deleted_models", lambda *args, **kwargs: None)
    caplog.set_level(logging.INFO, logger="cmdb")

    summary = DataCleanupService.run_daily_cleanup()

    assert aged["_id"] not in graph.rows
    by_id = {item["task_id"]: item for item in summary["results"]}
    assert by_id[good.id]["deleted_count"] == 1
    assert by_id[bad.id]["failed_count"] == 1
    assert by_id[bad.id]["deleted_count"] == 0
    errors = [record for record in caplog.records if record.levelname == "ERROR"]
    assert len(errors) == 1
    assert errors[0].msg == "[DataCleanup] task cleanup failed task_id=%s failed_stage=cleanup_expired_instances error_type=%s"
    assert errors[0].args == (bad.id, "RuntimeError")
    assert errors[0].exc_info[2] is not None
    finished = [record for record in caplog.records if record.msg.startswith("[DataCleanup] daily cleanup finished")]
    assert len(finished) == 1
    assert secret not in caplog.text
    assert secret not in str(summary)


@pytest.mark.parametrize(
    "family",
    [
        ("cloud", "qcloud", "qcloud_cvm"),
        ("cloud", "hwcloud", "hwcloud_ecs"),
        ("vm", "vmware_vc", "vmware_vm"),
        ("cloud", "netapp_ontap", "storage_volume"),
    ],
)
def test_real_plugin_errors_disable_deletion(family, monkeypatch):
    from apps.cmdb.collection.cleanup import snapshot_allows_cleanup

    kind, root, child = family
    cls = get_collection_plugin(kind, root)
    plugin = cls("platform", 1, "42", collect_inst=SimpleNamespace(model_id=root), snapshot_complete=True, round_ts=100, round_completed_at=101)
    error = {"metric": {"__name__": child + "_info_gauge", "collect_status": "success", "cmdb_collect_error": "failed"}, "value": [100, "1"]}
    monkeypatch.setattr(plugin, "query_data", lambda: {"result": [error]})
    plugin.run()
    assert not snapshot_allows_cleanup(plugin, child)


@pytest.mark.django_db
def test_pc_expiration_runs_only_on_complete_software_snapshot(monkeypatch):
    from apps.cmdb.models.change_record import DELETE_INST, ChangeRecord
    from apps.cmdb.services.pc_discovery import PCSnapshotReconciler
    from apps.cmdb.tests.test_pc_reconcile_service import InMemoryGraph, _snapshot, _task

    g = InMemoryGraph()
    monkeypatch.setattr("apps.cmdb.services.pc_discovery.GraphClient", lambda: g)
    task = _task(strategy="after_expiration", expire_days=3)
    pc = g.create_entity("instance", {"model_id": "pc", "inst_name": "WIN-ABC", "collect_task": task.id}, {}, [])
    software = g.create_entity("instance", {"model_id": "pc_software", "inst_name": "old", "collect_time": OLD}, {}, [])
    g.edges.append(dict(model_asst_id="pc_software_install_on_pc", asst_id="install_on", src_inst_id=software["_id"], dst_inst_id=pc["_id"]))
    reconciler = PCSnapshotReconciler(task)
    observed = datetime.fromisoformat(NOW)
    reconciler.apply(_snapshot(status="partial", collected_at=observed))
    assert "old" in g.store
    result = reconciler.apply(_snapshot(collected_at=observed + timedelta(seconds=1)))
    assert result["software_deleted"] == 1
    assert "WIN-ABC" in g.store and "old" not in g.store
    assert ChangeRecord.objects.filter(type=DELETE_INST, inst_id=software["_id"]).count() == 1


def test_concurrent_refresh_between_query_and_delete_preserves_instance(graph, monkeypatch):
    old = graph.insert("gone", "aliyun_ecs", owner=42, collect_time=OLD)
    query = graph.query_entity

    def refresh_after_query(label, params, **kwargs):
        result = query(label, params, **kwargs)
        if any(p["field"] == "collect_task" and p["type"] == "int=" for p in params):
            graph.rows[old["_id"]]["collect_time"] = NOW
        return result

    monkeypatch.setattr(graph, "query_entity", refresh_after_query)
    result = reconcile(graph, FAMILIES[0], "after_expiration")
    assert old["_id"] in graph.rows
    assert result["delete"][0]["_status"] == "failed"
    assert result["delete"][0]["_id"] == old["_id"]


def test_upsert_failure_prevents_deleting_other_instances_of_that_model(graph, monkeypatch):
    old = graph.insert("gone", "aliyun_ecs", owner=42, collect_time=OLD)
    graph.insert("present", "aliyun_ecs", owner="42", collect_time=OLD, vcpus=1)

    def fail(*a, **kw):
        raise RuntimeError("write failed")

    monkeypatch.setattr(graph, "set_entity_properties", fail)
    result = reconcile(graph, FAMILIES[0], "immediately", rows=[{"inst_name": "present", "vcpus": 2}])
    assert result["update"][0]["_status"] == "failed"
    assert old["_id"] in graph.rows


def test_delete_failure_then_retry_reports_actual_results(graph, monkeypatch):
    old = graph.insert("gone", "aliyun_ecs", owner=42, collect_time=OLD)
    delete = graph.detach_delete_entity

    def fail(*a, **kw):
        raise RuntimeError("delete failed")

    monkeypatch.setattr(graph, "detach_delete_entity", fail)
    result = reconcile(graph, FAMILIES[0], "after_expiration")
    assert result["delete"][0]["_status"] == "failed" and old["_id"] in graph.rows
    monkeypatch.setattr(graph, "detach_delete_entity", delete)
    result = reconcile(graph, FAMILIES[0], "after_expiration")
    assert result["delete"][0]["_status"] == "success" and old["_id"] not in graph.rows
    assert reconcile(graph, FAMILIES[0], "after_expiration")["delete"] == []


@pytest.mark.parametrize("missing_sample,expected_complete", [(False, True), (True, False)])
def test_k8s_checks_full_scrape_counts_before_empty_pod_cleanup(graph, monkeypatch, missing_sample, expected_complete):
    import time

    from apps.cmdb.collection.cleanup import snapshot_allows_cleanup
    from apps.cmdb.collection.collect_plugin.k8s import CollectK8sMetrics
    from apps.cmdb.collection.query_vm import Collection

    timestamp = int(time.time())
    from apps.cmdb.collection.constants import REPLICAS_METRICS

    names = set(CollectK8sMetrics.get_metrics()) | set(REPLICAS_METRICS)
    markers = [
        {
            "metric": {"__name__": "prometheus_cmdb_k8s_snapshot_count", "resource_metric": name.removeprefix("prometheus_")},
            "value": [timestamp, "1" if name == "prometheus_kube_namespace_labels" else "0"],
        }
        for name in names
    ]
    rows = [] if missing_sample else [{"metric": {"__name__": "prometheus_kube_namespace_labels", "namespace": "default"}, "value": [timestamp, "1"]}]

    def query(self, sql, **kwargs):
        return {
            "status": "success",
            "data": {"result": [{"metric": {}, "value": [timestamp, str(timestamp)]}] if "snapshot_timestamp" in sql else markers + rows},
        }

    monkeypatch.setattr(Collection, "query", query)
    plugin = CollectK8sMetrics("cluster")
    result = plugin.run()
    assert result["k8s_pod"] == []
    assert snapshot_allows_cleanup(plugin, "k8s_pod") is expected_complete


@pytest.mark.django_db
@pytest.mark.parametrize("strategy,deleted", [("no_cleanup", False), ("immediately", True), ("after_expiration", True)])
def test_vcenter_runner_cleans_child_models_and_protects_selected_root(graph, monkeypatch, strategy, deleted):
    from apps.cmdb.collection.collect_tasks.registry import RegisteredCollect
    from apps.cmdb.collection.query_vm import Collection
    from apps.cmdb.tests.test_vmware_collection_ownership_service import task

    root = graph.insert("VC", ip_addr="192.0.2.10")
    t = task(root, "vc-expiration", data_cleanup_strategy=strategy, expire_days=3)
    t._sync_snapshot_complete = True
    t._sync_round_ts = t._sync_round_completed_at = datetime.fromisoformat(NOW).timestamp()
    old = [graph.insert(model, model, owner=str(t.id), collect_time=OLD) for model in ("vmware_vm", "vmware_ds", "vmware_esxi")]
    monkeypatch.setattr(
        Collection,
        "query",
        lambda *a, **k: {
            "data": {
                "result": [
                    {
                        "metric": {"__name__": "vmware_vc_info_gauge", "collect_status": "success", "inst_name": "VC", "vc_version": "8"},
                        "value": [t._sync_round_ts, "1"],
                    }
                ]
            }
        },
    )
    _, result = RegisteredCollect(t.id, task=t).run()
    assert root["_id"] in graph.rows
    assert all((row["_id"] not in graph.rows) is deleted for row in old)
    assert len(result["delete"]) == (3 if deleted else 0)


# 已注册的多模型族共享同一真实落库入口，防止只修 VC / 阿里云。

MULTI_MODEL_FAMILIES = []
for registration in CollectionPluginRegistry.get_registry_snapshot():
    cls = get_collection_plugin(registration["task_type"], registration["model_id"])
    models = list(getattr(cls, "field_mappings", {}) or getattr(cls, "related_field_mappings", {}))
    children = [model for model in models if model != registration["model_id"] and model != "storage"]
    if len(models) > 1 and children:
        MULTI_MODEL_FAMILIES.append((registration["task_type"], registration["model_id"], children[0]))


@pytest.mark.parametrize("family", MULTI_MODEL_FAMILIES)
@pytest.mark.parametrize("strategy,deleted", [("no_cleanup", False), ("immediately", True), ("after_expiration", True)])
def test_registered_multi_model_families_apply_same_policy(graph, family, strategy, deleted):
    old = graph.insert("gone", family[2], owner="42", collect_time=OLD)
    result = reconcile(graph, family, strategy)
    assert (old["_id"] not in graph.rows) is deleted
    assert len(result["delete"]) == int(deleted)


@pytest.mark.parametrize(
    "root,child",
    [
        ("hwcloud", "hwcloud_ecs"),
        ("qcloud", "qcloud_cvm"),
        ("netapp_ontap", "storage_volume"),
        ("dell_unity", "storage_disk"),
        ("storage", "storage_pool"),
    ],
)
def test_skipped_invalid_identity_cannot_turn_partial_results_into_deletions(root, child, monkeypatch):
    from apps.cmdb.collection.cleanup import snapshot_allows_cleanup

    cls = get_collection_plugin("cloud", root)
    plugin = cls("platform", 1, "42", collect_inst=SimpleNamespace(model_id=root), snapshot_complete=True, round_ts=100, round_completed_at=101)
    # 真实指标名来自插件，不将无法识别的指标作为完整快照证据。
    metric_name = next(name for name in plugin._metrics if name.startswith(child + "_"))
    monkeypatch.setattr(
        plugin, "query_data", lambda: {"result": [{"metric": {"__name__": metric_name, "collect_status": "success"}, "value": [100, "1"]}]}
    )
    plugin.run()
    assert not snapshot_allows_cleanup(plugin, child)
