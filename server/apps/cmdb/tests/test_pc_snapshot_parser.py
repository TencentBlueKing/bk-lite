# -*- coding: utf-8 -*-
"""PC VM 快照解析器合同测试。

锁定 parse_pc_vm_rows：
- 完整/空/部分快照解析与安全门；
- 计数不匹配、错误计数、归属不符、重复实例名、快照 ID 不一致全部降级 partial；
- 多 PC 隔离；同一 PC 多轮快照只保留最新。
"""
from datetime import datetime, timezone

import pytest

from apps.cmdb.services.pc_discovery import parse_pc_vm_rows


def pc_metric(inst="WIN-AAA", snapshot="s1", status="complete", expected="1", errors="0", ts=1753200000, **fields):
    row = {
        "__name__": "pc_info",
        "bk_obj_id": "pc",
        "inst_name": inst,
        "host_name": "PC-01",
        "ip_addr": "10.0.0.8",
        "os_type": "windows",
        "snapshot_id": snapshot,
        "software_snapshot_status": status,
        "software_expected_count": expected,
        "software_error_count": errors,
        "_metric_time": ts,
    }
    row.update(fields)
    return row


def software_metric(pc_inst="WIN-AAA", snapshot="s1", inst="SW-001", name="Chrome", ts=1753200000, **fields):
    row = {
        "__name__": "pc_software_info",
        "bk_obj_id": "pc_software",
        "inst_name": inst,
        "pc_inst_name": pc_inst,
        "snapshot_id": snapshot,
        "software_key": "google chrome|google llc",
        "name": name,
        "version": "127.0",
        "publisher": "Google LLC",
        "source": "windows_registry",
        "_metric_time": ts,
    }
    row.update(fields)
    return row


def test_complete_snapshot_can_delete():
    snapshots = parse_pc_vm_rows([pc_metric(), software_metric()])
    assert len(snapshots) == 1
    snap = snapshots[0]
    assert snap.status == "complete"
    assert len(snap.software) == 1
    assert snap.can_delete is True
    assert snap.error_code == ""
    assert snap.collected_at == datetime.fromtimestamp(1753200000, tz=timezone.utc)


def test_complete_empty_snapshot_is_preserved():
    snapshots = parse_pc_vm_rows([pc_metric(status="complete", expected="0", errors="0")])
    assert len(snapshots) == 1
    assert snapshots[0].status == "complete"
    assert snapshots[0].software == ()
    assert snapshots[0].can_delete is True


def test_count_mismatch_downgrades_partial():
    rows = [pc_metric(status="complete", expected="2", errors="0"), software_metric()]
    snapshot = parse_pc_vm_rows(rows)[0]
    assert snapshot.status == "partial"
    assert snapshot.error_code == "SNAPSHOT_COUNT_MISMATCH"
    assert snapshot.can_delete is False


def test_error_count_downgrades_partial():
    rows = [pc_metric(status="complete", expected="1", errors="2"), software_metric()]
    snapshot = parse_pc_vm_rows(rows)[0]
    assert snapshot.status == "partial"
    assert snapshot.can_delete is False


def test_stargazer_partial_stays_partial():
    rows = [pc_metric(status="partial", expected="1", errors="0"), software_metric()]
    snapshot = parse_pc_vm_rows(rows)[0]
    assert snapshot.status == "partial"
    assert snapshot.error_code == "SOFTWARE_PARTIAL"
    assert snapshot.can_delete is False


def test_software_snapshot_id_mismatch_excluded():
    rows = [pc_metric(expected="1"), software_metric(snapshot="s0-old")]
    snapshot = parse_pc_vm_rows(rows)[0]
    assert snapshot.status == "partial"
    assert snapshot.can_delete is False


def test_duplicate_software_inst_name_downgrades():
    rows = [
        pc_metric(expected="2"),
        software_metric(inst="SW-001", name="Chrome"),
        software_metric(inst="SW-001", name="Chrome Dup"),
    ]
    snapshot = parse_pc_vm_rows(rows)[0]
    assert snapshot.status == "partial"
    assert snapshot.can_delete is False


def test_multi_pc_isolated():
    rows = [
        pc_metric(inst="WIN-AAA", snapshot="s1"),
        software_metric(pc_inst="WIN-AAA", snapshot="s1", inst="SW-001"),
        pc_metric(inst="WIN-BBB", snapshot="s2", status="partial", expected="3", errors="2"),
        software_metric(pc_inst="WIN-BBB", snapshot="s2", inst="SW-002"),
    ]
    snapshots = {snap.pc["inst_name"]: snap for snap in parse_pc_vm_rows(rows)}
    assert snapshots["WIN-AAA"].status == "complete"
    assert snapshots["WIN-AAA"].can_delete is True
    assert snapshots["WIN-BBB"].status == "partial"
    assert snapshots["WIN-BBB"].can_delete is False


def test_only_newest_snapshot_kept_per_pc():
    rows = [
        pc_metric(inst="WIN-AAA", snapshot="s1-old", ts=1753100000, expected="0"),
        pc_metric(inst="WIN-AAA", snapshot="s2-new", ts=1753200000, expected="1"),
        software_metric(pc_inst="WIN-AAA", snapshot="s2-new", ts=1753200000),
        software_metric(pc_inst="WIN-AAA", snapshot="s1-old", ts=1753100000, inst="SW-OLD"),
    ]
    snapshots = parse_pc_vm_rows(rows)
    assert len(snapshots) == 1
    assert snapshots[0].snapshot_id == "s2-new"
    assert snapshots[0].can_delete is True
