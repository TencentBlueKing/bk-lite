# -*- coding: utf-8 -*-
"""PC 白名单写入与多目标隔离合同测试。

锁定：
- 更新只写采集白名单字段，人工资产字段（asset_code/user/location 等）不被覆盖；
- IP/主机名变化不新建 PC（inst_name 是唯一身份）；
- 无效身份零写入；
- 同任务多台 PC 独立对账，一台失败不回滚另一台；
- 非权威任务命中零写入（SOURCE_TASK_CONFLICT）；
- 组织只在创建时写入，更新 payload 不出现 organization。
"""
from datetime import datetime, timezone

import pytest

from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.services.pc_discovery import (
    PC_COLLECTED_FIELDS,
    PCSnapshot,
    PCSnapshotReconciler,
    apply_pc_snapshots,
    filter_pc_payload,
)

T1 = datetime(2026, 7, 22, 10, 0, 0, tzinfo=timezone.utc)


class InMemoryGraph:
    """最小图存储 fake：query/create/set_properties/create_edge 直接操作字典。"""

    def __init__(self, fail_on_inst=None, fail_edges=False):
        self.store = {}  # inst_name -> entity dict
        self._next_id = 1
        self.fail_on_inst = fail_on_inst or set()
        self.fail_edges = fail_edges
        self.set_payloads = {}  # inst_name -> 最近一次更新 payload
        self.edges = []  # asso_info 列表

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def query_entity(self, label, params):
        model_id = next((p["value"] for p in params if p["field"] == "model_id"), None)
        inst_name = next((p["value"] for p in params if p["field"] == "inst_name"), None)
        items = [
            dict(entity)
            for entity in self.store.values()
            if entity.get("model_id") == model_id and (inst_name is None or entity.get("inst_name") == inst_name)
        ]
        return items, len(items)

    def create_entity(self, label, entity_info, check_attr_map, exist_items):
        if entity_info.get("inst_name") in self.fail_on_inst:
            raise RuntimeError("graph write boom with secret-ish detail " + "x" * 800)
        entity = dict(entity_info)
        entity["_id"] = self._next_id
        self._next_id += 1
        self.store[entity["inst_name"]] = entity
        return dict(entity)

    def set_entity_properties(self, label, ids, entity_info, check_attr_map, exist_items):
        entity = self.store.get(entity_info.get("inst_name"))
        if entity is None:
            raise RuntimeError("entity missing")
        if entity["inst_name"] in self.fail_on_inst:
            raise RuntimeError("graph write boom")
        self.set_payloads[entity["inst_name"]] = dict(entity_info)
        entity.update(entity_info)
        return [dict(entity)]

    def create_edge(self, label, src_id, src_label, dst_id, dst_label, asso_info, key):
        if self.fail_edges:
            raise RuntimeError("edge write boom")
        for edge in self.edges:
            if (edge["src_inst_id"], edge["dst_inst_id"], edge["asst_id"]) == (
                asso_info["src_inst_id"], asso_info["dst_inst_id"], asso_info["asst_id"],
            ):
                raise RuntimeError("edge already exists")
        self.edges.append(dict(asso_info))
        return dict(asso_info)


def _task(name="pc-task"):
    return CollectModels.objects.create(
        name=name,
        task_type=CollectPluginTypes.HOST,
        driver_type=CollectDriverTypes.JOB,
        model_id="pc",
        cycle_value_type="cycle",
        team=[7],
    )


def _snapshot(inst="WIN-ABC", software=(), status="complete", snapshot_id="s1", collected_at=T1, **pc_fields):
    pc = {
        "inst_name": inst,
        "host_name": "PC-01",
        "ip_addr": "10.0.0.8",
        "os_type": "windows",
        "os_name": "Windows 11",
        "logged_in_user": "ACME\\bob",
        "last_collect_time": "2026-07-22T10:00:00+00:00",
        "snapshot_id": snapshot_id,
        "software_snapshot_status": status,
        "software_expected_count": str(len(software)),
        "software_error_count": "0",
    }
    pc.update(pc_fields)
    return PCSnapshot(
        pc=pc,
        software=tuple(software),
        status=status,
        snapshot_id=snapshot_id,
        expected_count=len(software),
        error_count=0,
        collected_at=collected_at,
    )


@pytest.fixture
def graph(monkeypatch):
    fake = InMemoryGraph()
    monkeypatch.setattr(
        "apps.cmdb.services.pc_discovery.GraphClient", lambda *a, **k: fake
    )
    return fake


@pytest.mark.django_db
def test_filter_pc_payload_drops_unknown_fields():
    payload = filter_pc_payload({"inst_name": "WIN-A", "host_name": "x", "asset_code": "A-1", "evil": 1})
    assert payload == {"inst_name": "WIN-A", "host_name": "x"}
    assert "asset_code" not in PC_COLLECTED_FIELDS
    assert "user" not in PC_COLLECTED_FIELDS


@pytest.mark.django_db
def test_pc_update_only_writes_collected_whitelist(graph):
    task = _task()
    graph.store["WIN-ABC"] = {
        "_id": 42,
        "model_id": "pc",
        "inst_name": "WIN-ABC",
        "asset_code": "A-001",
        "user": "alice",
        "location": "Shanghai",
    }

    result = PCSnapshotReconciler(task).apply(_snapshot())

    saved = graph.store["WIN-ABC"]
    assert saved["asset_code"] == "A-001"
    assert saved["user"] == "alice"
    assert saved["location"] == "Shanghai"
    assert saved["logged_in_user"] == "ACME\\bob"
    payload = graph.set_payloads["WIN-ABC"]
    assert "organization" not in payload
    assert "asset_code" not in payload
    assert result["pc_status"] == "updated"
    assert result["pc_failed"] == 0


@pytest.mark.django_db
def test_ip_or_hostname_change_does_not_create_new_pc(graph):
    task = _task()
    graph.store["WIN-ABC"] = {
        "_id": 42,
        "model_id": "pc",
        "inst_name": "WIN-ABC",
        "ip_addr": "10.0.0.1",
        "host_name": "OLD-NAME",
    }

    result = PCSnapshotReconciler(task).apply(_snapshot(ip_addr="10.0.0.9", host_name="NEW-NAME"))

    assert result["pc_status"] == "updated"
    assert graph.store["WIN-ABC"]["_id"] == 42
    assert len(graph.store) == 1


@pytest.mark.django_db
def test_create_writes_organization_and_runtime_fields(graph):
    task = _task()

    result = PCSnapshotReconciler(task).apply(_snapshot())

    assert result["pc_status"] == "added"
    created = graph.store["WIN-ABC"]
    assert created["organization"] == 7
    assert created["model_id"] == "pc"
    assert created["auto_collect"] is True
    assert created["collect_task"] == task.id


@pytest.mark.django_db
@pytest.mark.parametrize(
    "pc_fields",
    [
        {"inst_name": ""},
        {"inst_name": "WIN-ABC", "os_type": "macos"},
        {"inst_name": "RANDOM-XYZ", "os_type": "windows"},
    ],
)
def test_invalid_identity_not_written(graph, pc_fields):
    task = _task()

    result = PCSnapshotReconciler(task).apply(_snapshot(**pc_fields))

    assert result["pc_failed"] == 1
    assert result["error_code"] == "PC_IDENTITY_INVALID"
    assert graph.store == {}


@pytest.mark.django_db
def test_multi_target_one_failure_does_not_rollback_other(monkeypatch):
    task = _task()
    fake = InMemoryGraph(fail_on_inst={"WIN-BAD"})
    monkeypatch.setattr("apps.cmdb.services.pc_discovery.GraphClient", lambda *a, **k: fake)

    outcome = apply_pc_snapshots(task, [_snapshot(inst="WIN-OK"), _snapshot(inst="WIN-BAD")])

    assert "WIN-OK" in fake.store
    assert "WIN-BAD" not in fake.store
    rows = {row["inst_name"]: row for row in outcome["results"]}
    assert rows["WIN-OK"]["_status"] == "success"
    assert rows["WIN-BAD"]["_status"] == "failed"
    assert rows["WIN-BAD"]["_error"] == "CMDB_WRITE_PARTIAL"
    assert len(rows["WIN-BAD"]["_error_detail"]) <= 500


@pytest.mark.django_db
def test_source_conflict_zero_writes(graph):
    owner = _task("owner")
    other = _task("other")
    PCSnapshotReconciler(owner).apply(_snapshot())

    result = PCSnapshotReconciler(other).apply(_snapshot(snapshot_id="s2", collected_at=datetime(2026, 7, 22, 11, tzinfo=timezone.utc)))

    assert result["pc_failed"] == 1
    assert result["error_code"] == "SOURCE_TASK_CONFLICT"
    assert graph.set_payloads == {}


# ---- Task 9: 软件 upsert 与 install_on 关联 ----


def _software(inst="SW-AAA", pc_inst="WIN-ABC", snapshot_id="s1", name="Chrome", version="126.0", **fields):
    row = {
        "inst_name": inst,
        "pc_inst_name": pc_inst,
        "snapshot_id": snapshot_id,
        "software_key": "chrome|google",
        "name": name,
        "version": version,
        "publisher": "Google",
        "source": "registry",
        "last_collect_time": "2026-07-22T10:00:00+00:00",
    }
    row.update(fields)
    return row


def _software_of(graph, pc_inst):
    """通过 install_on 边找出属于某台 PC 的软件（归属只走关联，不落字段）。"""
    pc_id = graph.store[pc_inst]["_id"]
    sw_ids = {e["src_inst_id"] for e in graph.edges if e["dst_inst_id"] == pc_id and e["asst_id"] == "install_on"}
    return {name: e for name, e in graph.store.items() if e.get("_id") in sw_ids}


@pytest.mark.django_db
def test_software_written_with_install_on_association(graph):
    task = _task()

    result = PCSnapshotReconciler(task).apply(_snapshot(software=[_software()]))

    assert result["software_failed"] == 0
    assert result["software_added"] == 1
    sw = graph.store["SW-AAA"]
    assert sw["model_id"] == "pc_software"
    assert sw["organization"] == 7
    assert sw["version"] == "126.0"
    assert len(graph.edges) == 1
    edge = graph.edges[0]
    assert edge["asst_id"] == "install_on"
    assert edge["model_asst_id"] == "pc_software_install_on_pc"
    assert edge["src_inst_id"] == sw["_id"]
    assert edge["dst_inst_id"] == graph.store["WIN-ABC"]["_id"]


@pytest.mark.django_db
def test_software_upgrade_updates_same_instance(graph):
    task = _task()
    reconciler = PCSnapshotReconciler(task)

    reconciler.apply(_snapshot(software=[_software(version="126.0")]))
    first = graph.store["SW-AAA"]["_id"]
    reconciler.apply(
        _snapshot(snapshot_id="s2", collected_at=datetime(2026, 7, 22, 11, tzinfo=timezone.utc),
                  software=[_software(snapshot_id="s2", version="127.0")])
    )

    assert graph.store["SW-AAA"]["_id"] == first
    assert graph.store["SW-AAA"]["version"] == "127.0"
    # 重复采集不重复建边（edge already exists 幂等成功）
    assert len(graph.edges) == 1


@pytest.mark.django_db
def test_software_isolated_across_pcs(graph):
    task = _task()

    apply_pc_snapshots(task, [
        _snapshot(inst="WIN-AAA", software=[_software(inst="SW-AAA", pc_inst="WIN-AAA")]),
        _snapshot(inst="WIN-BBB", software=[_software(inst="SW-BBB", pc_inst="WIN-BBB")]),
    ])

    assert set(_software_of(graph, "WIN-AAA")) == {"SW-AAA"}
    assert set(_software_of(graph, "WIN-BBB")) == {"SW-BBB"}
    pc_by_edge = {e["dst_inst_id"] for e in graph.edges}
    assert pc_by_edge == {graph.store["WIN-AAA"]["_id"], graph.store["WIN-BBB"]["_id"]}


@pytest.mark.django_db
def test_association_failure_blocks_delete(monkeypatch):
    task = _task()
    fake = InMemoryGraph(fail_edges=True)
    monkeypatch.setattr("apps.cmdb.services.pc_discovery.GraphClient", lambda *a, **k: fake)

    result = PCSnapshotReconciler(task).apply(_snapshot(software=[_software()]))

    assert result["allow_delete"] is False
    assert result["software_failed"] == 1
    assert result["error_code"] == "CMDB_WRITE_PARTIAL"
    # PC 与软件实体已写入，仅关联失败，不回滚
    assert "WIN-ABC" in fake.store
    assert "SW-AAA" in fake.store


@pytest.mark.django_db
def test_software_payload_whitelisted(graph):
    task = _task()

    PCSnapshotReconciler(task).apply(_snapshot(software=[_software(evil_field="x", snapshot_id="s1")]))

    sw = graph.store["SW-AAA"]
    assert "evil_field" not in sw
    assert "snapshot_id" not in sw
    assert "pc_inst_name" not in sw  # 归属只走 install_on 关联，不作为资产字段
