# -*- coding: utf-8 -*-
"""PC 软件过期清理合同测试。

锁定设计：after_expiration 策略下，定时清理只删除权威任务拥有 PC 下
collect_time 早于阈值的软件，严禁按 model_id=pc 走通用分支删除 PC 实体；
删除仍写 DELETE_INST 审计。
"""
from datetime import datetime, timedelta, timezone

import pytest

from apps.cmdb.constants.constants import DataCleanupStrategy
from apps.cmdb.models.change_record import DELETE_INST, ChangeRecord
from apps.cmdb.services.data_cleanup_service import DataCleanupService
from apps.cmdb.tests.test_pc_reconcile_service import InMemoryGraph, _task

OLD = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
FRESH = datetime.now(timezone.utc).isoformat()


@pytest.fixture
def graph(monkeypatch):
    fake = InMemoryGraph()
    monkeypatch.setattr("apps.cmdb.services.pc_discovery.GraphClient", lambda *a, **k: fake)
    monkeypatch.setattr("apps.cmdb.services.data_cleanup_service.GraphClient", lambda *a, **k: fake)
    return fake


def _set_collect_time(graph, inst, collect_time):
    graph.store[inst]["collect_time"] = collect_time


@pytest.mark.django_db
def test_cleanup_deletes_only_stale_software_and_audits(graph):
    task = _task(strategy=DataCleanupStrategy.AFTER_EXPIRATION, expire_days=7)
    pc = graph.create_entity("instance", {
        "model_id": "pc", "inst_name": "WIN-ABC", "collect_task": task.id, "collect_time": FRESH,
    }, {}, [])
    for sw_inst, ctime in (("SW-STALE", OLD), ("SW-FRESH", FRESH)):
        sw = graph.create_entity("instance", {
            "model_id": "pc_software", "inst_name": sw_inst, "collect_task": task.id, "collect_time": ctime,
        }, {}, [])
        graph.edges.append({
            "model_asst_id": "pc_software_install_on_pc",
            "src_model_id": "pc_software",
            "src_inst_id": sw["_id"],
            "dst_model_id": "pc",
            "dst_inst_id": pc["_id"],
            "asst_id": "install_on",
        })

    result = DataCleanupService.cleanup_expired_instances(task)

    assert result["deleted_count"] == 1
    assert "SW-STALE" not in graph.store
    assert "SW-FRESH" in graph.store
    assert "WIN-ABC" in graph.store
    record = ChangeRecord.objects.get(type=DELETE_INST, inst_id=result["deleted_ids"][0])
    assert record.before_data["inst_name"] == "SW-STALE"


@pytest.mark.django_db
def test_cleanup_never_deletes_pc_entities(graph):
    """通用分支按 collect_task+model_id=pc 会误删 PC 实体，PC 必须走软件专用分流。"""
    task = _task(strategy=DataCleanupStrategy.AFTER_EXPIRATION, expire_days=7)
    graph.create_entity("instance", {
        "model_id": "pc", "inst_name": "WIN-ABC", "collect_task": task.id, "collect_time": OLD,
    }, {}, [])

    result = DataCleanupService.cleanup_expired_instances(task)

    assert "WIN-ABC" in graph.store
    assert result["deleted_count"] == 0


@pytest.mark.django_db
def test_cleanup_only_touches_tasks_own_pcs(graph):
    task = _task("owner", strategy=DataCleanupStrategy.AFTER_EXPIRATION, expire_days=7)
    other = _task("other", strategy=DataCleanupStrategy.AFTER_EXPIRATION, expire_days=7)
    mine = graph.create_entity("instance", {
        "model_id": "pc", "inst_name": "WIN-MINE", "collect_task": task.id, "collect_time": FRESH,
    }, {}, [])
    theirs = graph.create_entity("instance", {
        "model_id": "pc", "inst_name": "WIN-THEIRS", "collect_task": other.id, "collect_time": FRESH,
    }, {}, [])
    for pc, sw_inst in ((mine, "SW-MINE"), (theirs, "SW-THEIRS")):
        sw = graph.create_entity("instance", {
            "model_id": "pc_software", "inst_name": sw_inst, "collect_time": OLD,
        }, {}, [])
        graph.edges.append({
            "model_asst_id": "pc_software_install_on_pc",
            "src_model_id": "pc_software",
            "src_inst_id": sw["_id"],
            "dst_model_id": "pc",
            "dst_inst_id": pc["_id"],
            "asst_id": "install_on",
        })

    DataCleanupService.cleanup_expired_instances(task)

    assert "SW-MINE" not in graph.store
    assert "SW-THEIRS" in graph.store
