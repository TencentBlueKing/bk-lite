"""VM snapshot storage, age, and count stay off disk used_gb and off metric labels."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from common.cmp.cloud_apis.resource_apis.cw_vmware import Vmware

POLICY = Path(__file__).resolve().parents[3] / "server/apps/monitor/support-files/plugins/Telegraf/http/vmware/policy.json"
METRICS = Path(__file__).resolve().parents[3] / "server/apps/monitor/support-files/plugins/Telegraf/http/vmware/metrics.json"
INFO = Path(__file__).resolve().parents[1] / "plugins/inputs/vmware_vc/vmware_info.py"
CW = Path(__file__).resolve().parents[1] / "common/cmp/cloud_apis/resource_apis/cw_vmware.py"

NOW = datetime.datetime(2026, 10, 25, 12, 0, 0, tzinfo=datetime.timezone.utc)


def _driver():
    return Vmware.__new__(Vmware)


def _file(key, size):
    return SimpleNamespace(key=key, size=size)


def _layout_snap(data_key, memory_key, file_keys):
    chain = SimpleNamespace(fileKey=file_keys)
    disk = SimpleNamespace(key=2000, chain=[chain])
    return SimpleNamespace(dataKey=data_key, memoryKey=memory_key, disk=[disk])


def _tree(*nodes):
    return SimpleNamespace(rootSnapshotList=list(nodes))


def _node(create_time, children=None, name="snap"):
    return SimpleNamespace(createTime=create_time, childSnapshotList=list(children or []), name=name)


def _vm(layout, snapshot, refresh=None):
    vm = SimpleNamespace(_moId="vm-1", layoutEx=layout, snapshot=snapshot)

    def _ok():
        return None

    vm.RefreshStorageInfo = refresh or _ok
    return vm


def test_no_snapshot_tree_reports_zeros():
    vm = _vm(layout=SimpleNamespace(file=[_file(1, 999)], snapshot=[]), snapshot=None)
    assert Vmware._compute_vm_snapshot_metrics(vm, NOW) == (0, 0, 0)
    empty = _vm(layout=None, snapshot=SimpleNamespace(rootSnapshotList=[]))
    assert Vmware._compute_vm_snapshot_metrics(empty, NOW) == (0, 0, 0)


def test_shared_file_key_counted_once_and_base_disk_excluded():
    layout = SimpleNamespace(
        file=[_file(1, 100), _file(2, 50), _file(3, 1000), _file(4, 80)],
        snapshot=[
            _layout_snap(1, -1, [1, 2]),
            _layout_snap(1, 4, [1]),
        ],
        disk=[SimpleNamespace(key=9, chain=[SimpleNamespace(fileKey=[3])])],
    )
    older = NOW - datetime.timedelta(days=10)
    newer = NOW - datetime.timedelta(days=2)
    vm = _vm(layout, _tree(_node(older, name="old"), _node(newer, name="new")))
    storage, age, count = Vmware._compute_vm_snapshot_metrics(vm, NOW)
    assert storage == 230
    assert count == 2
    assert age == 10 * 24 * 3600


def test_memory_key_negative_ignored():
    layout = SimpleNamespace(file=[_file(8, 40), _file(9, 999)], snapshot=[_layout_snap(8, -1, [])])
    vm = _vm(layout, _tree(_node(NOW - datetime.timedelta(seconds=5))))
    storage, _age, count = Vmware._compute_vm_snapshot_metrics(vm, NOW)
    assert storage == 40
    assert count == 1


def test_missing_create_time_still_counts_and_age_zero_when_none_valid():
    layout = SimpleNamespace(file=[_file(1, 10)], snapshot=[_layout_snap(1, -1, [])])
    vm = _vm(layout, _tree(_node(None), _node("")))
    storage, age, count = Vmware._compute_vm_snapshot_metrics(vm, NOW)
    assert storage == 10
    assert count == 2
    assert age == 0


def test_refresh_storage_info_error_still_returns_three_values():
    layout = SimpleNamespace(file=[_file(1, 7)], snapshot=[_layout_snap(1, -1, [])])

    def boom():
        raise RuntimeError("refresh denied")

    vm = _vm(layout, _tree(_node(NOW - datetime.timedelta(seconds=3))), refresh=boom)
    storage, age, count = Vmware._compute_vm_snapshot_metrics(vm, NOW)
    assert (storage, age, count) == (7, 3, 1)


def test_get_vm_disks_does_not_call_snapshot_refresh():
    disks_src = INFO.read_text(encoding="utf-8").split("def _get_vm_disks", 1)[1].split("\n    def ", 1)[0]
    assert "RefreshStorageInfo" not in disks_src
    assert "_compute_vm_snapshot_metrics" not in disks_src
    assert "_process_vm_snapshots" not in disks_src


def test_vm_default_metrics_treat_snapshots_as_special():
    driver = _driver()
    _obj_type, _vim_types, metrics = driver._determine_object_type_and_metrics([{"bk_obj_id": "vmware_vm"}], None)
    for name in ("snapshot_storage_bytes", "oldest_snapshot_age_seconds", "snapshot_count"):
        assert name in metrics
    batch, special = driver._categorize_metrics(metrics, "vm")
    for name in ("snapshot_storage_bytes", "oldest_snapshot_age_seconds", "snapshot_count"):
        assert name in special
    assert "power_state" in special
    assert "tools_status" in special
    assert "cpu.usage.average" in batch


def test_process_snapshots_writes_plain_values_and_keeps_power_on_error():
    driver = _driver()
    driver._convert_server_time_to_timestamp = lambda _s: 1_700_000_000
    ok = _vm(
        SimpleNamespace(file=[_file(1, 11)], snapshot=[_layout_snap(1, -1, [])]),
        _tree(_node(NOW - datetime.timedelta(seconds=9))),
    )
    ok._moId = "vm-ok"
    broken = MagicMock()
    broken._moId = "vm-broken"
    broken.RefreshStorageInfo.side_effect = RuntimeError("layout")
    type(broken).layoutEx = property(lambda _self: (_ for _ in ()).throw(RuntimeError("layout")))
    type(broken).snapshot = property(lambda _self: (_ for _ in ()).throw(RuntimeError("tree")))
    broken.summary.runtime.powerState = "poweredOn"
    ok.summary = SimpleNamespace(runtime=SimpleNamespace(powerState="poweredOn"))
    data = {"EndTime": "2026-10-25 12:00:00"}
    res = {}
    driver._process_vm_snapshots([ok, broken], data, res)
    driver._process_power_state([ok, broken], data, res)
    assert res["vm-ok"]["snapshot_storage_bytes"][0][1] == 11
    assert res["vm-ok"]["oldest_snapshot_age_seconds"][0][1] == 9
    assert res["vm-ok"]["snapshot_count"][0][1] == 1
    assert isinstance(res["vm-ok"]["snapshot_storage_bytes"], list)
    assert "snapshot_storage_bytes" not in res.get("vm-broken", {})
    assert res["vm-ok"]["power_state"][0][1] == 1
    assert res["vm-broken"]["power_state"][0][1] == 1
    source = CW.read_text(encoding="utf-8")
    process_src = source.split("def _process_vm_snapshots", 1)[1].split("\n    def ", 1)[0]
    assert "name=" not in process_src
    assert "createTime" not in process_src or "createTime" in source.split("def _snapshot_count_and_oldest", 1)[1].split("\n    def ", 1)[0]


def test_plugin_registers_snapshot_gauges_and_gt_policies():
    metrics = json.loads(METRICS.read_text(encoding="utf-8"))
    vm = next(obj for obj in metrics["objects"] if obj["name"] == "VM")
    by_name = {item["name"]: item for item in vm["metrics"]}
    expected = {
        "snapshot_storage_bytes_gauge": "bytes",
        "oldest_snapshot_age_seconds_gauge": "s",
        "snapshot_count_gauge": "counts",
    }
    for name, unit in expected.items():
        item = by_name[name]
        assert item["unit"] == unit
        assert 'resource_type="vmware_vm"' in item["query"]
        assert item["query"].startswith(name)
        assert item["dimensions"] == []
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    registered = {m["name"] for obj in metrics["objects"] for m in obj["metrics"]}
    for tmpl in policy["templates"]:
        assert tmpl["metric_name"] in registered
    by_metric = {t["metric_name"]: t for t in policy["templates"]}
    assert by_metric["snapshot_storage_bytes_gauge"]["threshold"][0] == {
        "level": "warning",
        "value": 2147483648,
        "method": ">",
    }
    assert by_metric["oldest_snapshot_age_seconds_gauge"]["threshold"][0] == {
        "level": "warning",
        "value": 2592000,
        "method": ">",
    }
    assert by_metric["snapshot_count_gauge"]["threshold"][0] == {"level": "warning", "value": 2, "method": ">"}
    assert by_metric["tools_status_gauge"]["algorithm"] == "last_over_time"
    assert by_metric["boot_time_gauge"]["algorithm"] == "changes"
