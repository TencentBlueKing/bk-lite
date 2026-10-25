"""VM tools_status is a special metric: 0/1/2/3 from guest.toolsStatus only."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from common.cmp.cloud_apis.resource_apis.cw_vmware import Vmware

POLICY = Path(__file__).resolve().parents[3] / "server/apps/monitor/support-files/plugins/Telegraf/http/vmware/policy.json"
METRICS = Path(__file__).resolve().parents[3] / "server/apps/monitor/support-files/plugins/Telegraf/http/vmware/metrics.json"


def _driver():
    return Vmware.__new__(Vmware)


def test_tools_status_maps_known_strings_and_skips_empty():
    driver = _driver()
    assert driver._tools_status_code("toolsOk") == 0
    assert driver._tools_status_code("toolsOld") == 1
    assert driver._tools_status_code("toolsNotInstalled") == 2
    assert driver._tools_status_code("toolsNotRunning") == 3
    assert driver._tools_status_code("") is None
    assert driver._tools_status_code(None) is None
    enum_ok = MagicMock()
    enum_ok.name = "toolsOk"
    assert driver._tools_status_code(enum_ok) == 0


def test_tools_status_mapping_does_not_read_tools_running_status():
    source = (Path(__file__).resolve().parents[1] / "common/cmp/cloud_apis/resource_apis/cw_vmware.py").read_text(encoding="utf-8")
    process_src = source.split("def _process_tools_status", 1)[1].split("\n    def ", 1)[0]
    map_src = source.split("def _tools_status_code", 1)[1].split("\n    def ", 1)[0]
    assert "toolsRunningStatus" not in process_src
    assert "toolsRunningStatus" not in map_src


def test_process_tools_status_skips_empty_and_keeps_power_state():
    driver = _driver()
    driver._convert_server_time_to_timestamp = lambda _s: 1_700_000_000
    ok = MagicMock()
    ok._moId = "vm-ok"
    ok.guest.toolsStatus = "toolsOk"
    ok.summary.runtime.powerState = "poweredOn"
    empty = MagicMock()
    empty._moId = "vm-empty"
    empty.guest.toolsStatus = ""
    empty.summary.runtime.powerState = "poweredOff"
    broken = MagicMock()
    broken._moId = "vm-broken"
    type(broken).guest = property(lambda _self: (_ for _ in ()).throw(RuntimeError("guest missing")))
    broken.summary.runtime.powerState = "poweredOn"
    data = {"EndTime": "2026-10-25 12:00:00"}
    res = {}
    driver._process_tools_status([ok, empty, broken], data, res)
    driver._process_power_state([ok, empty, broken], data, res)
    assert res["vm-ok"]["tools_status"][0][1] == 0
    assert "tools_status" not in res.get("vm-empty", {})
    assert "tools_status" not in res.get("vm-broken", {})
    assert res["vm-ok"]["power_state"][0][1] == 1
    assert res["vm-empty"]["power_state"][0][1] == 0
    assert res["vm-broken"]["power_state"][0][1] == 1


def test_vm_default_metrics_include_tools_status_as_special():
    driver = _driver()
    _obj_type, _vim_types, metrics = driver._determine_object_type_and_metrics([{"bk_obj_id": "vmware_vm"}], None)
    assert "tools_status" in metrics
    batch, special = driver._categorize_metrics(metrics, "vm")
    assert "tools_status" in special
    assert "power_state" in special
    assert "cpu.usage.average" in batch


def test_vmware_plugin_registers_tools_status_enum_and_policy():
    metrics = json.loads(METRICS.read_text(encoding="utf-8"))
    vm = next(obj for obj in metrics["objects"] if obj["name"] == "VM")
    item = next(m for m in vm["metrics"] if m["name"] == "tools_status_gauge")
    assert item["data_type"] == "Enum"
    assert "toolsOk" in item["unit"]
    assert 'resource_type="vmware_vm"' in item["query"]
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    assert policy["object"] == "VM"
    assert policy["plugin"] == "VMWare"
    tmpl = policy["templates"][0]
    assert tmpl["metric_name"] == "tools_status_gauge"
    assert tmpl["metric_name"] == item["name"]
    assert tmpl["algorithm"] == "last_over_time"
    assert tmpl["threshold"][0]["method"] == ">="
    assert tmpl["threshold"][0]["value"] == 1
    assert tmpl["threshold"][0]["level"] == "warning"
    assert "等于 1" in tmpl["description"]
