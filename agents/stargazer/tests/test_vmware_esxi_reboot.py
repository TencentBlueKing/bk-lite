"""ESXi boot_time / uptime_seconds: CMDB ISO only, monitor Unix seconds, no days conversion."""

from __future__ import annotations

import datetime
import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

from common.cmp.cloud_apis.resource_apis.cw_vmware import Vmware

POLICY = Path(__file__).resolve().parents[3] / "server/apps/monitor/support-files/plugins/Telegraf/http/vmware/policy.json"
METRICS = Path(__file__).resolve().parents[3] / "server/apps/monitor/support-files/plugins/Telegraf/http/vmware/metrics.json"
CW_VMWARE = Path(__file__).resolve().parents[1] / "common/cmp/cloud_apis/resource_apis/cw_vmware.py"


def _install_pyvmomi_stubs(monkeypatch):
    pyvim = types.ModuleType("pyVim")
    connect = types.ModuleType("pyVim.connect")
    connect.Disconnect = MagicMock()
    connect.SmartConnect = MagicMock()
    pyvim.connect = connect
    pyvmomi = types.ModuleType("pyVmomi")
    pyvmomi.vim = MagicMock()
    monkeypatch.setitem(sys.modules, "pyVim", pyvim)
    monkeypatch.setitem(sys.modules, "pyVim.connect", connect)
    monkeypatch.setitem(sys.modules, "pyVmomi", pyvmomi)


def _load_manage(monkeypatch):
    _install_pyvmomi_stubs(monkeypatch)
    sys.modules.pop("plugins.inputs.vmware_vc.vmware_info", None)
    from plugins.inputs.vmware_vc.vmware_info import VmwareManage

    return VmwareManage


def _host(*, moid, name, ip, version, boot_time, raise_boot=False):
    host = MagicMock()
    host._moId = moid
    host.name = name
    nic = MagicMock()
    nic.spec.ip.ipAddress = ip
    host.config.network.vnic = [nic]
    host.config.product.version = version
    host.hardware.memorySize = 8 * 1024 * 1024 * 1024
    host.summary.hardware.cpuModel = "Xeon"
    host.summary.hardware.numCpuCores = 8
    host.summary.hardware.numCpuThreads = 16
    host.datastore = []
    if raise_boot:
        type(host).runtime = property(lambda _self: (_ for _ in ()).throw(RuntimeError("bootTime missing")))
    else:
        host.runtime.bootTime = boot_time
    return host


def _cluster(hosts):
    cluster = MagicMock()
    cluster.host = hosts
    return cluster


def test_get_hosts_writes_iso_boot_time_and_omits_uptime(monkeypatch):
    VmwareManage = _load_manage(monkeypatch)
    manager = VmwareManage({"username": "u", "password": "p", "hostname": "vc"})
    boot = datetime.datetime(2026, 1, 2, 3, 4, 5, tzinfo=datetime.timezone.utc)
    ok = _host(moid="host-1", name="esxi-ok", ip="10.0.0.1", version="8.0.0", boot_time=boot)
    empty = _host(moid="host-2", name="esxi-empty", ip="10.0.0.2", version="7.0.3", boot_time=None)
    broken = _host(
        moid="host-3",
        name="esxi-broken",
        ip="10.0.0.3",
        version="8.0.1",
        boot_time=None,
        raise_boot=True,
    )
    manager.get_all_objs = lambda obj_type=None: [_cluster([ok, empty, broken])]
    rows = manager.get_hosts()
    by_id = {row["resource_id"]: row for row in rows}
    assert by_id["host-1"]["boot_time"] == boot.isoformat()
    assert by_id["host-2"]["boot_time"] == ""
    assert by_id["host-3"]["boot_time"] == ""
    for row in rows:
        assert "uptime_seconds" not in row
        assert row["ip_addr"].startswith("10.0.0.")
        assert row["esxi_version"]
        assert row["resource_id"].startswith("host-")


def _driver():
    return Vmware.__new__(Vmware)


def test_esxi_default_metrics_treat_boot_and_uptime_as_special():
    driver = _driver()
    _obj_type, _vim_types, metrics = driver._determine_object_type_and_metrics([{"bk_obj_id": "vmware_esxi"}], None)
    assert "boot_time" in metrics
    assert "uptime_seconds" in metrics
    batch, special = driver._categorize_metrics(metrics, "esxi")
    assert "boot_time" in special
    assert "uptime_seconds" in special
    assert "cpu.usage.average" not in batch
    assert "cpu_usage_average" in special


def test_process_esxi_boot_uptime_skips_errors_keeps_cpu_and_seconds():
    driver = _driver()
    driver._convert_server_time_to_timestamp = lambda _s: 1_700_000_000
    driver._convert_vmware_datetime_to_timestamp = lambda dt: 1_767_326_400
    driver._get_esxi_cpu_usage = lambda data=None: {
        "host-ok": (12.5, 1_700_000_000),
        "host-broken": (8.0, 1_700_000_000),
    }
    boot = datetime.datetime(2026, 1, 2, 3, 4, 0, tzinfo=datetime.timezone.utc)
    ok = MagicMock()
    ok._moId = "host-ok"
    ok.runtime.bootTime = boot
    ok.summary.quickStats.uptime = 86400
    broken = MagicMock()
    broken._moId = "host-broken"
    type(broken).runtime = property(lambda _self: (_ for _ in ()).throw(RuntimeError("runtime gone")))
    type(broken).summary = property(lambda _self: (_ for _ in ()).throw(RuntimeError("summary gone")))
    data = {"EndTime": "2026-10-25 12:00:00"}
    res = {}
    driver._process_esxi_boot_time([ok, broken], data, res)
    driver._process_esxi_uptime([ok, broken], data, res)
    driver._process_esxi_cpu_usage(data, res)
    assert res["host-ok"]["boot_time"][0][1] == 1_767_326_400
    assert res["host-ok"]["uptime_seconds"][0][1] == 86400
    assert "boot_time" not in res.get("host-broken", {})
    assert "uptime_seconds" not in res.get("host-broken", {})
    assert res["host-ok"]["cpu_usage_average"][0][1] == 12.5
    assert res["host-broken"]["cpu_usage_average"][0][1] == 8.0


def test_uptime_seconds_source_does_not_divide_by_days():
    source = CW_VMWARE.read_text(encoding="utf-8")
    process_src = source.split("def _process_esxi_uptime", 1)[1].split("\n    def ", 1)[0]
    assert "60 * 60 * 24" not in process_src
    assert "86400" not in process_src
    assert "esxi_sys_uptime_latest" not in process_src


def test_vmware_plugin_registers_esxi_reboot_gauges_and_boot_time_policy():
    metrics = json.loads(METRICS.read_text(encoding="utf-8"))
    esxi = next(obj for obj in metrics["objects"] if obj["name"] == "ESXI")
    by_name = {item["name"]: item for item in esxi["metrics"]}
    for name in ("boot_time_gauge", "uptime_seconds_gauge"):
        item = by_name[name]
        assert item["unit"] == "s"
        assert 'resource_type="vmware_esxi"' in item["query"]
        assert item["query"].startswith(name)
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    boot_tmpls = [t for t in policy["templates"] if t.get("metric_name") == "boot_time_gauge"]
    assert len(boot_tmpls) == 1
    tmpl = boot_tmpls[0]
    assert tmpl["metric_name"] == "boot_time_gauge"
    assert tmpl.get("object", policy["object"]) == "ESXI"
    assert tmpl["algorithm"] == "changes"
    assert tmpl["threshold"][0]["method"] == ">="
    assert tmpl["threshold"][0]["value"] == 1
    assert tmpl["threshold"][0]["level"] == "warning"
    assert not any(t.get("metric_name") in {"uptime_seconds", "uptime_seconds_gauge"} for t in policy["templates"])
    tools = next(t for t in policy["templates"] if t.get("metric_name") == "tools_status_gauge")
    assert tools["algorithm"] == "last_over_time"
