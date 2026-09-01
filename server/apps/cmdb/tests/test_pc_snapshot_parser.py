# -*- coding: utf-8 -*-
"""PC VM 快照解析器合同测试：资产行无快照标签，控制信息来自轮次元数据。"""

from datetime import datetime, timezone

import pytest

from apps.cmdb.collection.round_metadata import RoundMetadataProtocolError
from apps.cmdb.services.pc_discovery import parse_pc_vm_rows


def pc_metric(inst="WIN-AAA", target="10.0.0.8", ts=1753200000, **fields):
    row = {
        "__name__": "pc_info",
        "bk_obj_id": "pc",
        "inst_name": inst,
        "host_name": "PC-01",
        "ip_addr": target,
        "os_type": "windows",
        "collection_target": target,
        "_metric_time": ts,
    }
    row.update(fields)
    return row


def software_metric(pc_inst="WIN-AAA", target="10.0.0.8", inst="SW-001", name="Chrome", ts=1753200000, **fields):
    row = {
        "__name__": "pc_software_info",
        "bk_obj_id": "pc_software",
        "inst_name": inst,
        "pc_inst_name": pc_inst,
        "collection_target": target,
        "software_key": f"{name.lower()}|vendor",
        "name": name,
        "version": "127.0",
        "publisher": "Google LLC",
        "source": "windows_registry",
        "_metric_time": ts,
    }
    row.update(fields)
    return row


def round_metadata(target="10.0.0.8", ts=1753200000, snapshot="s1", status="complete", expected=1, errors=0):
    timestamp_ms = int(ts * 1000)
    return {
        (target, timestamp_ms): {
            "snapshot_id": snapshot,
            "snapshot_status": status,
            "details": {
                "software_expected_count": expected,
                "software_error_count": errors,
            },
        }
    }


def test_complete_snapshot_can_delete():
    snapshots = parse_pc_vm_rows([pc_metric(), software_metric()], round_metadata())
    assert len(snapshots) == 1
    snap = snapshots[0]
    assert snap.status == "complete"
    assert len(snap.software) == 1
    assert snap.can_delete is True
    assert snap.error_code == ""
    assert snap.collected_at == datetime.fromtimestamp(1753200000, tz=timezone.utc)


def test_complete_empty_snapshot_is_preserved():
    snapshots = parse_pc_vm_rows([pc_metric()], round_metadata(expected=0))
    assert snapshots[0].software == ()
    assert snapshots[0].can_delete is True


def test_count_mismatch_downgrades_partial():
    snapshot = parse_pc_vm_rows([pc_metric(), software_metric()], round_metadata(expected=2))[0]
    assert snapshot.error_code == "SNAPSHOT_COUNT_MISMATCH"
    assert snapshot.can_delete is False


def test_error_count_downgrades_partial():
    snapshot = parse_pc_vm_rows([pc_metric(), software_metric()], round_metadata(errors=2))[0]
    assert snapshot.status == "partial"
    assert snapshot.can_delete is False


def test_stargazer_partial_stays_partial():
    snapshot = parse_pc_vm_rows([pc_metric(), software_metric()], round_metadata(status="partial"))[0]
    assert snapshot.error_code == "SOFTWARE_PARTIAL"
    assert snapshot.can_delete is False


def test_software_from_another_round_is_excluded():
    rows = [pc_metric(), software_metric(ts=1753199999)]
    snapshot = parse_pc_vm_rows(rows, round_metadata())[0]
    assert snapshot.status == "partial"
    assert snapshot.can_delete is False


def test_duplicate_software_identity_downgrades():
    rows = [pc_metric(), software_metric(), software_metric(inst="SW-002")]
    snapshot = parse_pc_vm_rows(rows, round_metadata(expected=2))[0]
    assert snapshot.status == "partial"
    assert snapshot.can_delete is False


def test_multi_target_snapshots_are_isolated():
    rows = [
        pc_metric(inst="WIN-AAA"),
        software_metric(pc_inst="WIN-AAA"),
        pc_metric(inst="WIN-BBB", target="10.0.0.9"),
        software_metric(pc_inst="WIN-BBB", target="10.0.0.9", inst="SW-002", name="Firefox"),
    ]
    metadata = {
        **round_metadata(),
        **round_metadata(target="10.0.0.9", snapshot="s2", status="partial", expected=3, errors=2),
    }
    snapshots = {snap.pc["inst_name"]: snap for snap in parse_pc_vm_rows(rows, metadata)}
    assert snapshots["WIN-AAA"].can_delete is True
    assert snapshots["WIN-BBB"].can_delete is False


def test_only_newest_snapshot_kept_per_pc():
    rows = [
        pc_metric(ts=1753100000),
        pc_metric(ts=1753200000),
        software_metric(ts=1753200000),
    ]
    metadata = {
        **round_metadata(ts=1753100000, snapshot="s1-old", expected=0),
        **round_metadata(ts=1753200000, snapshot="s2-new", expected=1),
    }
    snapshots = parse_pc_vm_rows(rows, metadata)
    assert len(snapshots) == 1
    assert snapshots[0].snapshot_id == "s2-new"
    assert snapshots[0].can_delete is True


def test_missing_metadata_fails_before_reconciliation():
    with pytest.raises(RoundMetadataProtocolError, match="metadata_missing"):
        parse_pc_vm_rows([pc_metric()], {})
