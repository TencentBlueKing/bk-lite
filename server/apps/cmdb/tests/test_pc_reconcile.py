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
    """最小图存储 fake：query/create/set_properties 直接操作字典。"""

    def __init__(self, fail_on_inst=None):
        self.store = {}  # inst_name -> entity dict
        self._next_id = 1
        self.fail_on_inst = fail_on_inst or set()
        self.set_payloads = {}  # inst_name -> 最近一次更新 payload

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
