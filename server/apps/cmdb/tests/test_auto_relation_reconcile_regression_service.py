"""#5826：通过图存储边界验证真实收敛行为和查询规模。"""
from collections import Counter
from uuid import UUID

import pytest

from apps.cmdb.services import auto_relation_reconcile as mod
from apps.cmdb.services.auto_relation_reconcile import AutoRelationRuleReconcileService as SVC
from apps.cmdb.services.instance_identity import prepare_edge_endpoint_properties


def instance(i, model, key):
    return {"_id": i, "inst_uuid": str(UUID(int=i, version=4)), "model_id": model, "key": key, "unused_payload": "x" * 1024}


def association(name):
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


class MemoryGraph:
    def __init__(self, instances):
        self.instances = instances
        self.edges = []
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def query_entity(self, label, conditions, **kwargs):
        self.queries.append((conditions, kwargs))
        rows = self.instances
        for condition in conditions:
            field, op, value = (condition[k] for k in ("field", "type", "value"))
            if op == "id[]":
                rows = [row for row in rows if row["_id"] in value]
            elif op == "id>":
                rows = [row for row in rows if row["_id"] > value]
            else:
                rows = [row for row in rows if row.get(field) == value]
        rows = sorted(rows, key=lambda row: row["_id"])
        total = len(rows)
        if kwargs.get("page"):
            rows = rows[: kwargs["page"]["limit"]]
        if kwargs.get("fields") is not None:
            rows = [{field: row.get(field) for field in ["_id", *kwargs["fields"]]} for row in rows]
        return rows, total

    def query_edge(self, label, conditions):
        return [edge for edge in self.edges if all(edge.get(c["field"]) == c["value"] for c in conditions)]

    def create_edge(self, label, src_id, src_label, dst_id, dst_label, data, *args):
        by_id = {row["_id"]: row for row in self.instances}
        edge = prepare_edge_endpoint_properties(
            data,
            src_inst_uuid=by_id[src_id]["inst_uuid"],
            dst_inst_uuid=by_id[dst_id]["inst_uuid"],
        )
        assert not any(
            all(old.get(key) == edge[key] for key in ("src_inst_uuid", "dst_inst_uuid", "model_asst_id")) for old in self.edges
        ), "duplicate edge"
        edge["_id"] = len(self.edges) + 1
        self.edges.append(edge)

    def delete_edge(self, edge_id):
        self.edges[:] = [edge for edge in self.edges if edge["_id"] != edge_id]


@pytest.fixture
def graph(monkeypatch):
    graph = MemoryGraph([instance(1, "source", "a"), instance(2, "source", "b"), instance(11, "target", "a"), instance(12, "target", "b")])
    monkeypatch.setattr(mod, "GraphClient", lambda: graph)
    monkeypatch.setattr(mod, "model_association_search", lambda model: [association("r1"), association("r2")])
    monkeypatch.setattr("apps.cmdb.services.instance.InstanceManage.check_asso_mapping", lambda data: None)
    return graph


def test_persisted_uuid_edges_are_idempotent_and_stale_owned_edges_are_deleted(graph):
    assert SVC.reconcile_for_instances([1, 2])["created"] == 4
    second = SVC.reconcile_for_instances([1, 2])
    assert (second["created"], second["skipped"], second["failed"]) == (0, 4, [])
    graph.edges[0]["association_source"] = "manual"
    graph.instances[0]["key"] = "no-match"
    third = SVC.reconcile_for_instances([1])
    assert third["deleted"] == 1
    assert len(graph.edges) == 3
    assert graph.edges[0]["association_source"] == "manual"


def test_batch_reuses_target_snapshot_and_projects_only_matching_fields(graph, monkeypatch):
    reads = Counter()

    def associations(model):
        reads[model] += 1
        return [association("r1"), association("r2")]

    monkeypatch.setattr(mod, "model_association_search", associations)
    result = SVC.reconcile_for_instances([1, 2])
    assert result["created"] == 4
    target_queries = [kwargs for conditions, kwargs in graph.queries if conditions[0].get("value") == "target"]
    assert len(target_queries) == 1
    assert set(target_queries[0]["fields"]) == {"inst_uuid", "model_id", "key"}
    assert reads["source"] <= 2  # 每模型一次出向、一次入向查询


def test_exact_matching_does_not_scan_all_targets_per_source(graph, monkeypatch):
    graph.instances = [instance(i, "source", str(i)) for i in range(1, 101)] + [instance(1000 + i, "target", str(i)) for i in range(1, 1001)]
    matches = []
    original = SVC._matches_pair

    def match(src, dst, pair):
        matches.append(1)
        return original(src, dst, pair)

    monkeypatch.setattr(SVC, "_matches_pair", staticmethod(match))
    result = SVC.reconcile_for_instances(list(range(1, 101)))
    assert result["created"] == 200
    assert len(matches) <= 200


@pytest.mark.parametrize(
    "matching,src,targets",
    [
        ("exact", 0, [False, 0, "0", None, [], 1]),
        ("exact", [1], [[1], [2], None]),
        ("exact", {"a": 1}, [{"a": 1}, {}, None]),
        ("exact", frozenset({1}), [{1}, frozenset({1}), {2}]),
        ("iexact", " A ", ["a", " A ", "ab", None]),
        ("contains", "a", ["cat", "A", "b", None]),
        ("exact", "", ["", None, "a"]),
    ],
)
def test_index_keeps_original_match_semantics(matching, src, targets):
    from apps.cmdb.services.auto_relation_rule import AutoRelationMatchPair, AutoRelationRule
    from apps.cmdb.services.auto_relation_targets import TargetSnapshot

    pair = AutoRelationMatchPair("key", "key", matching)
    rule = AutoRelationRule("r", True, [pair])
    rows = [instance(i + 1, "target", value) for i, value in enumerate(targets)]
    expected = set() if SVC._is_empty_value(src) else {row["_id"] for row in rows if SVC._matches_pair(src, row["key"], pair)}
    assert SVC._calculate_desired_target_ids({"key": src}, {}, [rule], TargetSnapshot(rows)) == expected


def test_index_checks_all_pairs_and_unions_rules():
    from apps.cmdb.services.auto_relation_rule import AutoRelationMatchPair as Pair
    from apps.cmdb.services.auto_relation_rule import AutoRelationRule as Rule
    from apps.cmdb.services.auto_relation_targets import TargetSnapshot

    rows = [{"_id": 1, "key": "a", "name": "match"}, {"_id": 2, "key": "a", "name": "other"}, {"_id": 3, "key": "b"}]
    rules = [Rule("r1", True, [Pair("key", "key"), Pair("name", "name", "contains")]), Rule("r2", True, [Pair("other", "key")])]
    assert SVC._calculate_desired_target_ids({"key": "a", "name": "mat", "other": "b"}, {}, rules, TargetSnapshot(rows)) == {1, 3}


def test_snapshot_pages_past_database_result_limit(graph, monkeypatch):
    monkeypatch.setattr(mod, "AUTO_RELATION_BATCH_SIZE", 2)
    graph.instances = [instance(i, "target", str(i)) for i in range(5)]
    rows = SVC._query_instances_by_model("target", fields=["inst_uuid", "key"])
    assert [row["_id"] for row in rows] == list(range(5))
    assert len(graph.queries) == 3
    assert "unused_payload" not in rows[0]


def test_failed_snapshot_never_deletes_existing_edges(graph, monkeypatch):
    SVC.reconcile_for_instances([1, 2])
    graph.instances[0]["key"] = "no-match"
    previous = list(graph.edges)
    original = graph.query_entity

    def fail(label, conditions, **kwargs):
        if any(c.get("type") == "id>" for c in conditions):
            raise RuntimeError("target page unavailable")
        return original(label, conditions, **kwargs)

    monkeypatch.setattr(mod, "AUTO_RELATION_BATCH_SIZE", 1)
    monkeypatch.setattr(graph, "query_entity", fail)
    with pytest.raises(RuntimeError, match="target page unavailable"):
        SVC.reconcile_for_instances([1])
    assert graph.edges == previous


def test_large_dispatch_serial_batches_and_one_final_incoming_sync(monkeypatch):
    callbacks, dispatched = [], []
    monkeypatch.setattr(mod.transaction, "on_commit", callbacks.append)
    monkeypatch.setattr("celery.canvas._chain.apply_async", lambda self, **kwargs: dispatched.append(self))
    mod.schedule_instance_auto_relation_reconcile(list(range(1, 10002)))
    assert not dispatched
    callbacks[0]()
    tasks = list(dispatched[0].tasks)
    assert len(tasks) == 22
    assert [i for task in tasks[:-1] for i in task.args[0]] == list(range(1, 10002))
    assert all(len(task.args[0]) <= 500 and task.immutable and task.kwargs == {"schedule_incoming": False} for task in tasks[:-1])
    assert tasks[-1].task == mod.INCOMING_FULL_SYNC_TASK
    assert tasks[-1].immutable


def test_batch_chain_execution_emits_incoming_once_after_all_batches(graph, monkeypatch):
    from celery import Celery

    from apps.cmdb.tasks.celery_tasks import reconcile_instances_auto_association_task, sync_incoming_auto_association_task

    app = Celery("auto-relation-regression", set_as_current=False)
    app.conf.update(task_always_eager=True, task_eager_propagates=True)
    # 用真实 Celery chain 执行任务体，仅替换消息传输边界。
    app.task(name=mod.INSTANCE_BATCH_RECONCILE_TASK)(reconcile_instances_auto_association_task.run)
    app.task(name=mod.INCOMING_FULL_SYNC_TASK)(sync_incoming_auto_association_task.run)
    monkeypatch.setattr(mod, "current_app", app)
    monkeypatch.setattr(mod, "AUTO_RELATION_BATCH_SIZE", 1)
    monkeypatch.setattr(mod.transaction, "on_commit", lambda callback: callback())
    associations = [association("r1"), dict(association("incoming"), src_model_id="elsewhere", dst_model_id="source")]
    monkeypatch.setattr(mod, "model_association_search", lambda model: associations)
    scheduled = []
    monkeypatch.setattr(mod, "schedule_rule_auto_relation_full_sync", lambda ids: scheduled.append((list(ids), len(graph.edges))))
    mod.schedule_instance_auto_relation_reconcile([1, 2])
    assert scheduled == [(["incoming"], 2)]
    assert len(graph.edges) == 2


def test_full_sync_uuid_idempotency(graph, monkeypatch):
    monkeypatch.setattr(mod, "model_association_info_search", lambda key: association(key))
    assert SVC.full_sync_rule("r1")["created"] == 2
    repeat = SVC.full_sync_rule("r1")
    assert (repeat["created"], repeat["skipped"], repeat["conflicts"]) == (0, 2, 0)


def test_shared_target_projection_unions_fields_across_source_models(graph, monkeypatch):
    graph.instances[1]["model_id"] = "other-source"
    graph.instances[1]["other"] = "c"
    graph.instances[3]["other"] = "c"
    first, second = association("r1"), association("r2")
    second["src_model_id"] = "other-source"
    second["auto_relation_rule"]["rules"][0]["match_pairs"][0].update(src_field_id="other", dst_field_id="other")
    monkeypatch.setattr(mod, "model_association_search", lambda model: [first, second])
    result = SVC.reconcile_for_instances([1, 2])
    assert result["created"] == 2
    target_queries = [kwargs for conditions, kwargs in graph.queries if conditions[0]["value"] == "target"]
    assert len(target_queries) == 1
    assert set(target_queries[0]["fields"]) == {"model_id", "inst_uuid", "key", "other"}


def test_reconcile_reports_failed_instance_and_continues_other_sources(graph, monkeypatch):
    original = graph.query_edge

    def fail_first_source(label, conditions):
        if any(c["value"] == graph.instances[0]["inst_uuid"] for c in conditions):
            raise RuntimeError("graph unavailable")
        return original(label, conditions)

    monkeypatch.setattr(graph, "query_edge", fail_first_source)
    result = SVC.reconcile_for_instances([1, 2])
    assert result["success"] is False
    assert result["failed"] == [{"instance_id": 1, "error": "graph unavailable"}]
    assert result["created"] == 2
    assert all(edge["src_inst_uuid"] == graph.instances[1]["inst_uuid"] for edge in graph.edges)
