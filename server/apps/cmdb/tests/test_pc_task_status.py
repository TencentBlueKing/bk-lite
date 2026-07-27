# -*- coding: utf-8 -*-
"""PC 任务状态聚合合同测试。

锁定：
- merge_task_format_data 把 pc_summary 与逐 PC 行合并进 format_data；
- celery 摘要复制 pc_summary；
- 完整空软件快照（raw_data 为空）不误判 ERROR；
- 逐 PC 行驱动全部失败 ERROR / 混合 PARTIAL_SUCCESS / 全成功 SUCCESS 的既有口径。
"""
from datetime import datetime, timezone

import pytest

from apps.cmdb.collection.collect_tasks.base import BaseCollect
from apps.cmdb.constants.constants import CollectRunStatusType
from apps.cmdb.tasks.celery_tasks import (
    _apply_pc_digest,
    _decide_collect_exec_status,
)
from apps.cmdb.tests.test_pc_reconcile import _snapshot, _software, _task
from apps.cmdb.services.pc_discovery import apply_pc_snapshots

T1 = datetime(2026, 7, 22, 10, 0, 0, tzinfo=timezone.utc)


def test_merge_task_format_data_copies_pc_summary_and_rows():
    format_data = {"add": [], "update": [], "delete": [], "association": []}
    collect_data = {
        "__task_format_data__": {
            "update": [{"inst_name": "WIN-ABC", "_status": "success"}],
            "all": 1,
            "pc_summary": {"pc_complete": 1, "pc_failed": 0},
        }
    }

    merged = BaseCollect.merge_task_format_data(format_data, collect_data)

    assert merged["update"] == [{"inst_name": "WIN-ABC", "_status": "success"}]
    assert merged["pc_summary"] == {"pc_complete": 1, "pc_failed": 0}
    assert merged["all"] == 1


def test_apply_pc_digest_copies_summary():
    digest = {"add": 0, "update": 1}
    summary = _apply_pc_digest(digest, {"pc_summary": {"pc_failed": 1, "source_conflict": 0}})

    assert summary == {"pc_failed": 1, "source_conflict": 0}
    assert digest["pc_summary"] == {"pc_failed": 1, "source_conflict": 0}
    assert _apply_pc_digest({}, {}) is None


def test_complete_empty_snapshot_not_marked_error():
    """raw_data 为空但 pc_summary 存在且逐 PC 行全成功 → SUCCESS，不以空原始数据误判。"""
    status = _decide_collect_exec_status(
        {"update": 1, "update_error": 0, "add": 0, "add_error": 0, "delete": 0, "delete_error": 0,
         "association": 0, "association_error": 0, "collect_success": 0, "collect_failed": 0},
        raw_data=[],
        pc_summary={"pc_complete": 1, "pc_failed": 0},
    )
    assert status == CollectRunStatusType.SUCCESS


def test_all_failed_targets_marked_error():
    status = _decide_collect_exec_status(
        {"update": 2, "update_error": 2, "add": 0, "add_error": 0, "delete": 0, "delete_error": 0,
         "association": 0, "association_error": 0, "collect_success": 0, "collect_failed": 2},
        raw_data=[{"__time__": "t"}],
        pc_summary={"pc_complete": 0, "pc_failed": 2},
    )
    assert status == CollectRunStatusType.ERROR


def test_mixed_targets_marked_partial():
    status = _decide_collect_exec_status(
        {"update": 2, "update_error": 1, "add": 0, "add_error": 0, "delete": 0, "delete_error": 0,
         "association": 0, "association_error": 0, "collect_success": 1, "collect_failed": 1},
        raw_data=[{"__time__": "t"}],
        pc_summary={"pc_complete": 1, "pc_failed": 1},
    )
    assert status == CollectRunStatusType.PARTIAL_SUCCESS


def test_empty_raw_data_without_pc_summary_still_error():
    status = _decide_collect_exec_status(
        {"update": 0, "update_error": 0, "add": 0, "add_error": 0, "delete": 0, "delete_error": 0,
         "association": 0, "association_error": 0, "collect_success": 0, "collect_failed": 0},
        raw_data=[],
        pc_summary=None,
    )
    assert status == CollectRunStatusType.ERROR


@pytest.mark.django_db
def test_apply_pc_snapshots_format_data_rows_drive_digest(graph_and_task):
    """format_data 是逐 PC 行（非计数），pc_summary 汇总各状态分类。"""
    task = graph_and_task
    outcome = apply_pc_snapshots(task, [
        _snapshot(inst="WIN-OK", software=[_software(pc_inst="WIN-OK", inst="SW-OK")]),
        _snapshot(inst="BAD-IDENTITY", os_type="windows"),
    ])

    format_data = outcome["format_data"]
    assert format_data["all"] == 2
    statuses = {row["inst_name"]: row["_status"] for row in format_data["add"] + format_data["update"]}
    assert statuses["WIN-OK"] == "success"
    assert statuses["BAD-IDENTITY"] == "failed"
    summary = format_data["pc_summary"]
    assert summary["pc_failed"] == 1
    assert summary["software_added"] == 1


@pytest.fixture
def graph_and_task(db, monkeypatch):
    from apps.cmdb.tests.test_pc_reconcile import InMemoryGraph
    fake = InMemoryGraph()
    monkeypatch.setattr("apps.cmdb.services.pc_discovery.GraphClient", lambda *a, **k: fake)
    return _task("pc-digest-task")
