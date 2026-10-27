# -*- coding: utf-8 -*-
"""PC 软件身份读取必须按固定 100 条批量查询，不能再逐条 query_entity。"""
import pytest

from apps.cmdb.services.pc_discovery import PCSnapshotReconciler
from apps.cmdb.tests.test_pc_reconcile_service import InMemoryGraph, _snapshot, _software, _task

_BATCH = 100


class CountingGraph(InMemoryGraph):
    """记录软件身份读取，批量结果可注入重复名称以锁定“只保留第一条”。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.software_identity_reads = []
        self.pc_identity_reads = []
        self.software_batch_reads = []
        self.updated_ids = []
        self.forced_batch_rows = None

    def query_entity(self, label, params):
        model_id = next((item["value"] for item in params if item["field"] == "model_id"), None)
        has_inst_name = any(item["field"] == "inst_name" for item in params)
        inst_name = next((item["value"] for item in params if item["field"] == "inst_name"), None)
        if model_id == "pc_software" and has_inst_name:
            self.software_identity_reads.append(inst_name)
        elif model_id == "pc" and has_inst_name:
            self.pc_identity_reads.append(inst_name)
        return super().query_entity(label, params)

    def query_entity_by_inst_names(self, inst_names, model_id=None):
        self.software_batch_reads.append({"names": list(inst_names), "model_id": model_id})
        if self.forced_batch_rows is not None:
            return [dict(row) for row in self.forced_batch_rows]
        return super().query_entity_by_inst_names(inst_names, model_id=model_id)

    def set_entity_properties(self, label, ids, entity_info, check_attr_map, exist_items):
        updated = super().set_entity_properties(label, ids, entity_info, check_attr_map, exist_items)
        self.updated_ids.append(list(ids))
        return updated


def _names(count):
    return [f"SW-{index:03d}" for index in range(count)]


def _chunks(names, size=_BATCH):
    return [names[start : start + size] for start in range(0, len(names), size)]


def _seed(graph, names, version="1", organization=99):
    for offset, name in enumerate(names, start=1000):
        graph.store[name] = {
            "_id": offset,
            "model_id": "pc_software",
            "inst_name": name,
            "version": version,
            "organization": organization,
        }
    graph._next_id = 1000 + len(names) + 1


def _apply(monkeypatch, graph, software, task_name="pc-task"):
    monkeypatch.setattr("apps.cmdb.services.pc_discovery.GraphClient", lambda *a, **k: graph)
    return PCSnapshotReconciler(_task(name=task_name)).apply(_snapshot(software=software))


def _assert_pc_still_read_by_name(graph):
    assert graph.pc_identity_reads == ["WIN-ABC"]


@pytest.mark.django_db
def test_existing_software_identity_reads_are_batched(monkeypatch):
    cases = ((1, [1]), (10, [10]), (100, [100]), (101, [100, 1]))
    runs = []
    for count, chunk_sizes in cases:
        names = _names(count)
        graph = CountingGraph()
        _seed(graph, names, version="1")
        result = _apply(monkeypatch, graph, [_software(inst=name, version="9") for name in names], task_name=f"pc-batch-{count}")
        runs.append((names, chunk_sizes, graph, result))

    observed = {
        len(names): {
            "identity_query_entity": len(graph.software_identity_reads),
            "batch_calls": len(graph.software_batch_reads),
            "chunk_sizes": [len(call["names"]) for call in graph.software_batch_reads],
        }
        for names, _chunk_sizes, graph, _result in runs
    }
    expected = {
        1: {"identity_query_entity": 0, "batch_calls": 1, "chunk_sizes": [1]},
        10: {"identity_query_entity": 0, "batch_calls": 1, "chunk_sizes": [10]},
        100: {"identity_query_entity": 0, "batch_calls": 1, "chunk_sizes": [100]},
        101: {"identity_query_entity": 0, "batch_calls": 2, "chunk_sizes": [100, 1]},
    }
    mismatches = [
        f"{count}: identity={observed[count]['identity_query_entity']} batch={observed[count]['batch_calls']} chunks={observed[count]['chunk_sizes']}"
        for count in expected
        if observed[count] != expected[count]
    ]
    if mismatches:
        raise AssertionError("software identity still read per item: " + "; ".join(mismatches))
    for names, chunk_sizes, graph, result in runs:
        assert [call["names"] for call in graph.software_batch_reads] == _chunks(names)
        assert [call["model_id"] for call in graph.software_batch_reads] == ["pc_software"] * len(chunk_sizes)
        assert graph.software_identity_reads == []
        _assert_pc_still_read_by_name(graph)
        assert result["software_updated"] == len(names)
        assert result["software_added"] == 0
        assert result["software_failed"] == 0
        assert graph.updated_ids == [[1000 + index] for index in range(len(names))]
        for index, name in enumerate(names):
            assert graph.store[name]["version"] == "9"
            assert graph.store[name]["_id"] == 1000 + index
            assert graph.store[name]["organization"] == 99
            assert "organization" not in graph.set_payloads[name]


@pytest.mark.django_db
def test_missing_software_is_created_from_one_batch_read(monkeypatch):
    graph = CountingGraph()
    result = _apply(monkeypatch, graph, [_software(inst="SW-NEW", version="3"), _software(inst="SW-NEXT", version="9")])

    assert graph.software_batch_reads == [{"names": ["SW-NEW", "SW-NEXT"], "model_id": "pc_software"}]
    assert graph.software_identity_reads == []
    _assert_pc_still_read_by_name(graph)
    assert result["software_added"] == 2
    assert result["software_updated"] == 0
    assert result["software_failed"] == 0
    assert graph.store["SW-NEW"]["model_id"] == "pc_software"
    assert graph.store["SW-NEW"]["version"] == "3"
    assert graph.store["SW-NEXT"]["version"] == "9"
    assert {edge["src_inst_id"] for edge in graph.edges} == {graph.store["SW-NEW"]["_id"], graph.store["SW-NEXT"]["_id"]}


@pytest.mark.django_db
def test_one_update_failure_does_not_block_the_next(monkeypatch):
    graph = CountingGraph(fail_on_inst={"SW-000"})
    _seed(graph, ["SW-000", "SW-001"], version="1")

    result = _apply(monkeypatch, graph, [_software(inst="SW-000", version="9"), _software(inst="SW-001", version="8")])

    assert graph.software_batch_reads == [{"names": ["SW-000", "SW-001"], "model_id": "pc_software"}]
    assert graph.software_identity_reads == []
    assert result["software_failed"] == 1
    assert result["software_updated"] == 1
    assert result["outcomes"] == [("SW-000", "failed"), ("SW-001", "success")]
    assert graph.store["SW-000"]["version"] == "1"
    assert graph.store["SW-001"]["version"] == "8"
    assert graph.updated_ids == [[1001]]


@pytest.mark.django_db
def test_edge_failure_after_create_deletes_orphan(monkeypatch):
    graph = CountingGraph(fail_edges=True)

    result = _apply(monkeypatch, graph, [_software(inst="SW-AAA")])

    assert graph.software_batch_reads == [{"names": ["SW-AAA"], "model_id": "pc_software"}]
    assert graph.software_identity_reads == []
    assert result["software_failed"] == 1
    assert result["software_added"] == 0
    assert result["outcomes"] == [("SW-AAA", "failed")]
    assert "WIN-ABC" in graph.store
    assert "SW-AAA" not in graph.store


@pytest.mark.django_db
def test_duplicate_batch_hit_keeps_first_entity(monkeypatch):
    graph = CountingGraph()
    graph.store["SW-AAA"] = {"_id": 101, "model_id": "pc_software", "inst_name": "SW-AAA", "version": "1", "organization": 99}
    graph.forced_batch_rows = [
        {"_id": 100, "model_id": "pc_software", "inst_name": "SW-AAA", "version": "1", "organization": 99},
        {"_id": 101, "model_id": "pc_software", "inst_name": "SW-AAA", "version": "1", "organization": 99},
    ]

    result = _apply(monkeypatch, graph, [_software(inst="SW-AAA", version="9")])

    assert graph.software_identity_reads == []
    assert graph.updated_ids == [[100]]
    assert result["software_updated"] == 1
    assert graph.store["SW-AAA"]["organization"] == 99
    assert "organization" not in graph.set_payloads["SW-AAA"]


@pytest.mark.django_db
def test_same_snapshot_duplicate_name_updates_the_created_row(monkeypatch):
    graph = CountingGraph()

    result = _apply(monkeypatch, graph, [_software(inst="SW-AAA", version="1"), _software(inst="SW-AAA", version="2")])

    assert graph.software_batch_reads == [{"names": ["SW-AAA"], "model_id": "pc_software"}]
    assert graph.software_identity_reads == []
    assert result["software_added"] == 1
    assert result["software_updated"] == 1
    assert result["software_failed"] == 0
    assert graph.store["SW-AAA"]["version"] == "2"
    assert len(graph.edges) == 1


@pytest.mark.django_db
def test_blank_software_name_does_not_query(monkeypatch):
    graph = CountingGraph()

    result = _apply(monkeypatch, graph, [{}, {"inst_name": "", "name": "Empty"}])

    assert graph.software_batch_reads == []
    assert graph.software_identity_reads == []
    assert result["software_failed"] == 1
    assert result["software_added"] == 1
    assert graph.store[""]["name"] == "Empty"
