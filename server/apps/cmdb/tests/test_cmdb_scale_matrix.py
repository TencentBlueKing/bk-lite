"""1000 / 5000 / 10000 实例规模矩阵。图库替身只记录 FalkorDB 查询，不连接 Neo4j。"""

import threading
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.cmdb.collection.metrics_cannula import MetricsCannula
from apps.cmdb.constants.subscription import TriggerType
from apps.cmdb.graph.falkordb import FalkorDBClient
from apps.cmdb.models.auto_relation_pending import AutoRelationPending
from apps.cmdb.models.subscription_rule import SubscriptionRule
from apps.cmdb.services import auto_relation_reconcile as auto_mod
from apps.cmdb.services.auto_relation_reconcile import AUTO_RELATION_BATCH_SIZE, AUTO_RELATION_SOURCE_BUDGET
from apps.cmdb.services.auto_relation_reconcile import AutoRelationRuleReconcileService as AutoSVC
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.scale_cursor import load_scale_cursor, save_scale_cursor
from apps.cmdb.services.subscription_task import SubscriptionTaskService
from apps.cmdb.services.subscription_trigger import SubscriptionTriggerService
from apps.cmdb.services.unique_rule import (
    ModelUniqueRule,
    _collect_existing_instance_conflicts,
    _iter_model_instances,
)
from apps.cmdb.services.unique_write_lock import UniqueWriteLockService
from apps.cmdb.tasks.celery_tasks import _clip_collect_format_data
from apps.core.exceptions.base_app_exception import BaseAppException

SIZES = [1000, 5000, 10000]


class _RecordingGraph:
    def __init__(self, rows):
        self.rows = list(rows)
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def query_entity(self, label, conditions, **kwargs):
        self.queries.append((list(conditions), kwargs))
        rows = self.rows
        for condition in conditions:
            field, op, value = condition["field"], condition["type"], condition["value"]
            if op == "id>":
                rows = [row for row in rows if row["_id"] > value]
            elif op == "str[]":
                wanted = set(value)
                rows = [row for row in rows if row.get(field) in wanted]
            elif op == "id[]":
                rows = [row for row in rows if row["_id"] in set(value)]
            else:
                rows = [row for row in rows if row.get(field) == value]
        rows = sorted(rows, key=lambda row: row["_id"])
        limit = (kwargs.get("page") or {}).get("limit")
        if limit is not None:
            rows = rows[:limit]
        if kwargs.get("fields") is not None:
            # 图客户端的字段投影始终带回内部节点 ID。
            rows = [{field: row.get(field) for field in dict.fromkeys(["_id", *kwargs["fields"]])} for row in rows]
        return rows, len(rows)


class _EdgeGraph:
    def __init__(self, edges):
        self.edges = edges
        self.calls = []
        self._lock = threading.Lock()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def query_edge(self, label, params, return_entity=True):
        with self._lock:
            self.calls.append(list(params))
        matched = []
        for item in self.edges:
            edge = item["edge"]
            if all(self._matches(edge, param) for param in params):
                matched.append(item)
        return matched

    @staticmethod
    def _matches(edge, param):
        value = edge.get(param["field"])
        if param["type"] == "str[]":
            return value in set(param["value"])
        return value == param["value"]


def _node(node_id):
    node = SimpleNamespace(id=node_id, labels=["instance"], properties={"model_id": "host", "inst_name": str(node_id)})
    return node


def _topo_client(neighbors):
    client = FalkorDBClient.__new__(FalkorDBClient)
    client.asked = []

    def execute(query, params=None):
        ids = [int(item) for item in (params or {}).get("ids", [])]
        client.asked.append(ids)
        nodes = {}
        edges = []
        for src in ids:
            for dst in neighbors.get(src, []):
                nodes.setdefault(src, _node(src))
                nodes.setdefault(dst, _node(dst))
                edges.append(
                    SimpleNamespace(
                        id=src * 100000 + dst,
                        relation="instance_association",
                        properties={"model_asst_id": "link"},
                        src_node=nodes[src],
                        dest_node=nodes[dst],
                    )
                )
        if not edges:
            return SimpleNamespace(result_set=[])
        return SimpleNamespace(result_set=[[SimpleNamespace(_nodes=list(nodes.values()), _edges=edges)]])

    client._execute_query = execute
    return client


def _count_tree(node):
    if not isinstance(node, dict) or not node:
        return 0
    return 1 + sum(_count_tree(child) for child in node.get("children") or [])


def _association(name):
    return {
        "model_asst_id": name,
        "src_model_id": "source",
        "dst_model_id": "target",
        "mapping": "n:n",
        "auto_relation_rule": {
            "version": 1,
            "rules": [
                {
                    "rule_id": name,
                    "enabled": True,
                    "match_pairs": [{"src_field_id": "key", "dst_field_id": "key", "matching_rule": "exact"}],
                }
            ],
        },
    }


@pytest.mark.parametrize("size", SIZES)
def test_association_queries_stay_on_the_instance_uuid(size, monkeypatch):
    wanted = str(uuid4())
    edges = []
    for index in range(size):
        edges.append(
            {
                "edge": {
                    "_id": index + 1,
                    "model_asst_id": "other",
                    "src_inst_uuid": str(uuid4()),
                    "dst_inst_uuid": str(uuid4()),
                    "src_model_id": "host",
                    "dst_model_id": "app",
                    "asst_id": "run",
                },
                "src": {"inst_uuid": str(uuid4()), "model_id": "host"},
                "dst": {"inst_uuid": str(uuid4()), "model_id": "app"},
            }
        )
    graph = _EdgeGraph(edges)
    monkeypatch.setenv("FALKORDB_HOST", "scale-test")
    monkeypatch.setattr("apps.cmdb.services.instance.GraphClient", lambda: graph)
    empty = InstanceManage.instance_association_instance_list_by_uuid("host", wanted)
    assert empty == []
    assert graph.calls
    assert all(graph.calls)
    assert all(any(param["field"].endswith("inst_uuid") and param["value"] == wanted for param in call) for call in graph.calls)
    assert len(graph.calls) == 4

    matched = {
        "edge": {
            "_id": size + 1,
            "model_asst_id": "host_run_app",
            "src_inst_uuid": wanted,
            "dst_inst_uuid": str(uuid4()),
            "src_model_id": "host",
            "dst_model_id": "app",
            "asst_id": "run",
        },
        "src": {"inst_uuid": wanted, "model_id": "host", "inst_name": "me"},
        "dst": {"inst_uuid": str(uuid4()), "model_id": "app", "inst_name": "app"},
    }
    hit_graph = _EdgeGraph([*edges, matched])
    hit_graph.calls.clear()
    monkeypatch.setattr("apps.cmdb.services.instance.GraphClient", lambda: hit_graph)
    groups = InstanceManage.instance_association_instance_list_by_uuid("host", wanted)
    assert len(hit_graph.calls) == 2
    assert groups[0]["inst_count"] == 1
    assert groups[0]["inst_list"][0]["inst_name"] == "app"
    assert all(any(param["value"] == wanted for param in call) for call in hit_graph.calls)

    if size != 10000:
        return
    identities = [str(uuid4()) for _ in range(10)]
    shared = _EdgeGraph(edges)
    monkeypatch.setattr("apps.cmdb.services.instance.GraphClient", lambda: shared)

    def query_one(inst_uuid):
        InstanceManage.instance_association_instance_list_by_uuid("host", inst_uuid)

    threads = [threading.Thread(target=query_one, args=(inst_uuid,)) for inst_uuid in identities]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(shared.calls) == 40
    seen = set()
    for call in shared.calls:
        values = {param["value"] for param in call if param["field"].endswith("inst_uuid")}
        assert len(values) == 1
        seen.update(values)
    assert seen == set(identities)


@pytest.mark.parametrize("size", SIZES)
def test_falkordb_topo_is_one_hop_and_capped(size):
    chain = {1: [2], 2: [3], 3: [4]}
    client = _topo_client(chain)
    result = client.query_topo_lite("instance", 1, depth=3)
    assert len(client._last_topo_queries) == 3
    assert all("[*" not in query for query in client._last_topo_queries)
    assert _count_tree(result["src_result"]) <= 100
    assert client.asked == [[1], [2], [3]]
    delegated = client.query_topo("instance", 1)
    assert delegated["src_result"]["_id"] == 1
    assert all("[*" not in query for query in client._last_topo_queries)

    star = {1: list(range(2, size + 2))}
    wide = _topo_client(star)
    wide_result = wide.query_topo_lite("instance", 1, depth=3)
    assert _count_tree(wide_result["src_result"]) <= 100
    assert wide_result["src_result"]["has_more"] is True
    assert all("[*" not in query and "[*1.." not in query for query in wide._last_topo_queries)
    assert max(len(ids) for ids in wide.asked) < size

    if size != 10000:
        return
    left = _topo_client({1: [2], 2: [3]})
    right = _topo_client({8000: [8001], 8001: [8002]})
    left.query_topo_lite("instance", 1, depth=3)
    right.query_topo_lite("instance", 8000, depth=3)
    assert all(node_id < 100 for ids in left.asked for node_id in ids)
    assert all(node_id >= 8000 for ids in right.asked for node_id in ids)


@pytest.mark.django_db
@pytest.mark.parametrize("size", SIZES)
def test_auto_relation_pages_exact_targets(size, monkeypatch):
    assert AUTO_RELATION_BATCH_SIZE <= 500
    assert AUTO_RELATION_SOURCE_BUDGET == 2000
    rows = [{"_id": index, "model_id": "source", "inst_uuid": str(uuid4()), "key": f"s-{index}"} for index in range(1, size + 1)]
    rows.append({"_id": size + 1, "model_id": "target", "inst_uuid": str(uuid4()), "key": "s-1"})
    rows.extend(
        {"_id": size + 1 + index, "model_id": "target", "inst_uuid": str(uuid4()), "key": f"t-{index}"} for index in range(1, size + 1)
    )
    graph = _RecordingGraph(rows)
    rule_name = f"scale-rule-{size}"
    AutoRelationPending.objects.create(model_asst_id=rule_name, phase="delete", cursor_id=0)
    monkeypatch.setattr(auto_mod, "GraphClient", lambda: graph)
    monkeypatch.setattr(auto_mod, "model_association_info_search", lambda key: _association(key))
    monkeypatch.setattr(auto_mod, "AUTO_RELATION_SOURCE_BUDGET", 500)
    monkeypatch.setattr(AutoSVC, "_query_instances_by_model", classmethod(lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("loaded every target"))))

    def quiet(*args, **kwargs):
        return {"created": 0, "deleted": 0, "skipped": 1, "conflicts": 0}

    monkeypatch.setattr(AutoSVC, "reconcile_source_instance", classmethod(lambda cls, *args, **kwargs: quiet()))
    finished = False
    for _ in range(80):
        summary = AutoSVC.full_sync_rule(rule_name)
        if summary["done"]:
            finished = True
            break
    assert finished
    assert summary["source_instances"] <= 500
    source_pages = [kwargs for conditions, kwargs in graph.queries if conditions and conditions[0].get("value") == "source"]
    target_pages = [conditions for conditions, kwargs in graph.queries if any(item.get("value") == "target" for item in conditions)]
    assert source_pages
    assert all(kwargs["page"]["limit"] <= 500 for kwargs in source_pages)
    assert target_pages
    assert all(any(item["type"] == "str[]" and len(item["value"]) <= 500 for item in conditions) for conditions in target_pages)
    assert any(any(item["type"] == "id>" for item in conditions) for conditions, kwargs in graph.queries)
    from apps.cmdb.tasks.celery_tasks import _AutoRelationPendingSingleton

    assert _AutoRelationPendingSingleton.lock_expiry == 5 * 60
    assert _AutoRelationPendingSingleton.raise_on_duplicate is False


@pytest.mark.parametrize("size", SIZES)
def test_collect_reconcile_pages_and_clips(size):
    rows = [{"_id": index, "model_id": "router", "collect_task": "7", "inst_uuid": str(index), "inst_name": str(index)} for index in range(1, size + 1)]
    graph = _RecordingGraph(rows)
    cannula = MetricsCannula.__new__(MetricsCannula)
    cannula.task_id = "7"
    cannula.organization = []
    cannula._reconcile_for = lambda model_id: None
    cannula._query_task_assets(graph, "router", [])
    assert graph.queries
    assert all(kwargs["page"]["limit"] <= 500 for conditions, kwargs in graph.queries)
    assert all("inst_uuid" in kwargs["fields"] and "collect_task" in kwargs["fields"] for conditions, kwargs in graph.queries)
    if size != 10000:
        return
    payload = {"rows": [{"body": "x" * 64} for _ in range(60_000)]}
    clipped = _clip_collect_format_data(payload)
    assert len(clipped["rows"]) <= 50_000
    encoded = len(__import__("json").dumps(clipped).encode())
    assert encoded <= 64 * 1024 * 1024


@pytest.mark.django_db
@pytest.mark.parametrize("size", SIZES)
def test_attribute_subscription_uses_change_window(size, monkeypatch):
    graph_calls = []
    monkeypatch.setattr(
        "apps.cmdb.services.subscription_trigger.ModelManage.search_model_info",
        lambda model_id: {"model_id": model_id, "model_name": model_id},
    )
    monkeypatch.setattr(
        SubscriptionTriggerService,
        "_get_current_instances",
        lambda self, checkpoint: graph_calls.append("instances") or [],
    )
    monkeypatch.setattr(
        "apps.cmdb.services.subscription_trigger.InstanceManage.instance_list",
        staticmethod(lambda *args, **kwargs: graph_calls.append("instance_list") or ([], 0)),
    )
    rule = SubscriptionRule.objects.create(
        name=f"scale-sub-{size}",
        organization=1,
        model_id="host",
        filter_type="instances",
        instance_filter={},
        trigger_types=[TriggerType.ATTRIBUTE_CHANGE.value],
        trigger_config={"attribute_change": {"fields": ["inst_name"]}},
        recipients={},
        channel_ids=[],
        is_enabled=True,
        snapshot_data={"instances": list(range(1, size + 1))},
    )
    with CaptureQueriesContext(connection) as captured:
        SubscriptionTriggerService(rule).process()
    sql = "\n".join(item["sql"] for item in captured.captured_queries)
    assert "changerecord" in sql
    assert "created_at" in sql
    assert graph_calls == []
    rule.refresh_from_db()
    if size != 10000:
        return
    checked_at = rule.last_check_time
    with UniqueWriteLockService.serialize("cmdb-subscription-check", lease_seconds=30):
        SubscriptionTaskService.check_rules()
    rule.refresh_from_db()
    assert rule.last_check_time == checked_at


@pytest.mark.django_db
@pytest.mark.parametrize("size", SIZES)
def test_display_sync_resumes_from_cursor(size, monkeypatch):
    from apps.cmdb.display_field import sync as sync_mod
    from apps.cmdb.display_field.cache import ExcludeFieldsCache

    rows = [{"_id": index, "model_id": "host"} for index in range(1, size + 1)]
    graph = _RecordingGraph(rows)
    monkeypatch.setattr(sync_mod, "GraphClient", lambda: graph)
    monkeypatch.setattr(ExcludeFieldsCache, "get_model_fields_mapping", staticmethod(lambda: {"host": {"organization": ["org"], "user": []}}))
    monkeypatch.setattr(sync_mod, "_update_instance_page", lambda ag, instances, *args: (len(instances), 0))
    monkeypatch.setattr(sync_mod, "_get_sync_batch_size", lambda: 500)
    clock = {"now": 0}

    def monotonic():
        clock["now"] += 1
        return clock["now"]

    monkeypatch.setattr(sync_mod.time, "monotonic", monotonic)
    monkeypatch.setattr(sync_mod, "DISPLAY_SYNC_BUDGET_SECONDS", 0)
    first = sync_mod.DisplayFieldSynchronizer.sync_all({"organizations": [{"id": 1, "name": "平台"}], "users": []})
    assert first["done"] is False
    assert first["organizations"] == 500
    recorded = len(graph.queries)
    monkeypatch.setattr(sync_mod.time, "monotonic", time.monotonic)
    monkeypatch.setattr(sync_mod, "DISPLAY_SYNC_BUDGET_SECONDS", 180)
    second = sync_mod.DisplayFieldSynchronizer.sync_all({"organizations": [{"id": 1, "name": "平台"}], "users": []})
    assert second.get("done") is not False
    assert second["organizations"] == size
    assert load_scale_cursor("cmdb-display-field-sync") == {}
    resumed = graph.queries[recorded]
    assert any(item["type"] == "id>" and item["value"] == 500 for item in resumed[0])
    if size != 10000:
        return
    save_scale_cursor("cmdb-display-field-sync", {"cursor": 500, "organizations": 500, "users": 0})
    with UniqueWriteLockService.serialize("cmdb-display-field-sync", lease_seconds=30):
        with pytest.raises(TimeoutError):
            with UniqueWriteLockService.serialize("cmdb-display-field-sync", lease_seconds=30):
                pass
    assert load_scale_cursor("cmdb-display-field-sync")["cursor"] == 500


@pytest.mark.django_db
@pytest.mark.parametrize("size", SIZES)
def test_unique_rule_pages_match_a_full_scan(size):
    rows = [{"_id": index, "inst_uuid": str(uuid4()), "model_id": "host", "serial": "dup" if index in {1, 2} else f"s-{index}"} for index in range(1, size + 1)]
    graph = _RecordingGraph(rows)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("apps.cmdb.graph.drivers.graph_client.GraphClient", lambda: graph)
    try:
        paged = list(_iter_model_instances("host", ["_id", "inst_uuid", "serial"]))
    finally:
        monkeypatch.undo()
    rule = ModelUniqueRule(rule_id="serial", order=1, field_ids=["serial"])
    full_conflict = _collect_existing_instance_conflicts([rule], rows, {})[0]
    paged_conflict = _collect_existing_instance_conflicts([rule], paged, {})[0]
    assert len(paged) == size
    assert full_conflict.exist_instance_ids == paged_conflict.exist_instance_ids == [1]
    assert all(kwargs["page"]["limit"] <= 500 for conditions, kwargs in graph.queries)
    assert all("serial" in kwargs["fields"] and "_id" in kwargs["fields"] for conditions, kwargs in graph.queries)
    if size != 10000:
        return
    with UniqueWriteLockService.hold(["cmdb:unique-rules:host"]):
        with pytest.raises(BaseAppException, match="相同唯一键正在写入"):
            with UniqueWriteLockService.hold(["cmdb:unique-rules:host"]):
                pass
