# -*- coding: utf-8 -*-
"""HostCollectMetrics 纯辅助方法测试（不连 DB/VM，model_id 打桩为 host）。

覆盖：IP 解析、实例名/组件名生成、数值转换、MAC 规范化、OS/CPU 架构映射、
进程聚合、cloud 标签拼接、关联实例构造。断言真实输出与各分支早返回。
"""
import json

import pytest

from apps.cmdb.collection.collect_plugin.host import HostCollectMetrics


@pytest.fixture
def runner(monkeypatch):
    # model_id 属性会触发 DB 查询；纯方法测试直接桩为 "host"
    monkeypatch.setattr(HostCollectMetrics, "model_id", property(lambda self: "host"))
    return HostCollectMetrics("web01", "cmdb_1", 1)


def _runner_empty_name(monkeypatch):
    """构造一个 inst_name 为空的 runner，但不触发 DB（带名构造后清空）。"""
    monkeypatch.setattr(HostCollectMetrics, "model_id", property(lambda self: "host"))
    r = HostCollectMetrics("placeholder", "cmdb_1", 1)
    r.inst_name = ""
    return r


# --------------------------------------------------------------------------
# IP 解析
# --------------------------------------------------------------------------


def test_extract_ip_from_instance_id():
    assert HostCollectMetrics._extract_ip_from_instance_id("cmdb_10.0.0.5") == "10.0.0.5"
    assert HostCollectMetrics._extract_ip_from_instance_id("nounderscore") == ""
    assert HostCollectMetrics._extract_ip_from_instance_id("") == ""
    assert HostCollectMetrics._extract_ip_from_instance_id(None) == ""


def test_extract_ip_from_inst_name():
    assert HostCollectMetrics._extract_ip_from_inst_name("10.0.0.5[云A]") == "10.0.0.5"
    assert HostCollectMetrics._extract_ip_from_inst_name("10.0.0.6") == "10.0.0.6"
    assert HostCollectMetrics._extract_ip_from_inst_name("") == ""


def test_set_ip_addr_prefers_host(runner):
    assert runner.set_ip_addr({"host": "1.2.3.4"}) == "1.2.3.4"


def test_set_ip_addr_falls_back_to_instance_id(runner):
    assert runner.set_ip_addr({"instance_id": "cmdb_5.6.7.8"}) == "5.6.7.8"


def test_set_ip_addr_falls_back_to_inst_name(runner):
    # 无 host / instance_id → 退回 self.inst_name（web01，无 [ ]）
    assert runner.set_ip_addr({}) == "web01"


def test_set_ip_addr_unknown_when_nothing(monkeypatch):
    r = _runner_empty_name(monkeypatch)
    assert r.set_ip_addr({}) == "unknown"


# --------------------------------------------------------------------------
# 实例名 / 组件名
# --------------------------------------------------------------------------


def test_set_inst_name_uses_existing(runner):
    assert runner.set_inst_name({}) == "web01"


def test_set_inst_name_from_host(monkeypatch):
    r = _runner_empty_name(monkeypatch)
    assert r.set_inst_name({"host": "9.9.9.9"}) == "9.9.9.9"


def test_set_inst_name_from_instance_id(monkeypatch):
    r = _runner_empty_name(monkeypatch)
    assert r.set_inst_name({"instance_id": "cmdb_3.3.3.3"}) == "3.3.3.3"


def test_set_inst_name_unknown(monkeypatch):
    r = _runner_empty_name(monkeypatch)
    assert r.set_inst_name({}) == "unknown"


def test_set_component_inst_name_existing(runner):
    assert runner.set_component_inst_name({"model_id": "nic"}) == "web01"


@pytest.mark.parametrize(
    "model_id,extra,expected",
    [
        ("nic", {"nic_pci_addr": "0000:01", "self_device": "h1"}, "0000:01-h1"),
        ("disk", {"disk_name": "sda", "self_device": "h1"}, "sda-h1"),
        ("memory", {"mem_locator": "DIMM0", "self_device": "h1"}, "DIMM0-h1"),
        ("gpu", {"gpu_name": "A100", "self_device": "h1"}, "A100-h1"),
    ],
)
def test_set_component_inst_name_by_model(monkeypatch, model_id, extra, expected):
    r = _runner_empty_name(monkeypatch)
    data = {"model_id": model_id, **extra}
    assert r.set_component_inst_name(data) == expected


def test_set_component_inst_name_no_self_device(monkeypatch):
    r = _runner_empty_name(monkeypatch)
    assert r.set_component_inst_name({"model_id": "nic"}) == ""


# --------------------------------------------------------------------------
# 数值转换
# --------------------------------------------------------------------------


def test_transform_int():
    assert HostCollectMetrics.transform_int("3.0") == 3
    assert HostCollectMetrics.transform_int("7") == 7


def test_transform_unit_int():
    assert HostCollectMetrics.transform_unit_int(None) == 0
    assert HostCollectMetrics.transform_unit_int(5) == 5
    assert HostCollectMetrics.transform_unit_int(5.9) == 5
    assert HostCollectMetrics.transform_unit_int("1,024 MB") == 1024
    assert HostCollectMetrics.transform_unit_int("16.5GB") == 16
    assert HostCollectMetrics.transform_unit_int("no-number") == 0


# --------------------------------------------------------------------------
# MAC
# --------------------------------------------------------------------------


def test_format_mac_normalizes():
    assert HostCollectMetrics.format_mac("aa-bb-cc-dd-ee-ff") == "AA:BB:CC:DD:EE:FF"
    assert HostCollectMetrics.format_mac("AA:BB:CC:DD:EE:FF") == "AA:BB:CC:DD:EE:FF"


def test_format_mac_invalid_returned_lowercased_colon():
    # 非法 MAC 不通过正则校验，按真实实现返回「小写 + 横杠转冒号」后的原串（不大写）。
    assert HostCollectMetrics.format_mac("Not-A-Mac") == "not:a:mac"


# --------------------------------------------------------------------------
# OS / CPU 架构映射
# --------------------------------------------------------------------------


def test_set_os_type(runner):
    assert runner.set_os_type({"os_type": "Linux 5.10"}) == "1"
    assert runner.set_os_type({"os_type": "Windows Server"}) == "2"
    assert runner.set_os_type({"os_type": ""}) == "other"
    assert runner.set_os_type({"os_type": "Plan9"}) == "other"


def test_set_serverarch_type(runner):
    assert runner.set_serverarch_type({"cpu_arch": "x86_64"}) == "x64"
    assert runner.set_serverarch_type({"cpu_arch": "aarch64"}) == "arm64"
    assert runner.set_serverarch_type({"cpu_arch": ""}) == "other"
    assert runner.set_serverarch_type({"cpu_arch": "sparc"}) == "other"


# --------------------------------------------------------------------------
# 进程聚合
# --------------------------------------------------------------------------


def test_get_host_proc_key():
    assert HostCollectMetrics.get_host_proc_key({"ip_addr": "1.1.1.1"}) == "1.1.1.1"
    assert HostCollectMetrics.get_host_proc_key({"host": "h"}) == "h"
    assert HostCollectMetrics.get_host_proc_key({"instance_id": "id"}) == "id"
    assert HostCollectMetrics.get_host_proc_key({}) == ""


def test_add_and_get_host_proc(runner):
    runner.add_host_proc({"ip_addr": "1.1.1.1", "pid": "100", "name": "nginx", "ports": "80"})
    runner.add_host_proc({"ip_addr": "1.1.1.1", "pid": "200", "name": "redis"})
    out = json.loads(runner.get_host_proc({"ip_addr": "1.1.1.1"}))
    assert len(out) == 2
    assert out[0]["name"] == "nginx"
    assert out[0]["ports"] == "80"
    assert out[1]["pid"] == "200"


def test_add_host_proc_no_key_noop(runner):
    runner.add_host_proc({"pid": "1"})  # 无 ip/host/instance_id → 不入库
    assert runner.host_proc_map == {}
    assert json.loads(runner.get_host_proc({})) == []


# --------------------------------------------------------------------------
# cloud / display 名 / 关联
# --------------------------------------------------------------------------


def _fake_task(instances=None, params=None):
    class _T:
        pass

    t = _T()
    t.instances = instances if instances is not None else []
    t.params = params if params is not None else {}
    return t


def test_set_cloud_from_matched_instance(monkeypatch, runner):
    task = _fake_task(instances=[{"ip_addr": "1.2.3.4", "cloud": "aliyun"}])
    monkeypatch.setattr(runner, "get_collect_inst", lambda: task)
    assert runner.set_cloud({"host": "1.2.3.4"}) == "aliyun"


def test_set_cloud_from_cloud_id(monkeypatch, runner):
    task = _fake_task(instances=[{"ip_addr": "1.2.3.4", "cloud_id": "cid-9"}])
    monkeypatch.setattr(runner, "get_collect_inst", lambda: task)
    assert runner.set_cloud({"host": "1.2.3.4"}) == "cid-9"


def test_set_cloud_empty_when_none(monkeypatch, runner):
    task = _fake_task(instances=[{"ip_addr": "1.2.3.4"}])
    monkeypatch.setattr(runner, "get_collect_inst", lambda: task)
    assert runner.set_cloud({"host": "1.2.3.4"}) == ""


def test_set_display_inst_name_with_cloud_label(monkeypatch, runner):
    task = _fake_task(instances=[{"ip_addr": "1.2.3.4", "cloud_name": "阿里云"}])
    monkeypatch.setattr(runner, "get_collect_inst", lambda: task)
    assert runner.set_display_inst_name({"host": "1.2.3.4"}) == "1.2.3.4[阿里云]"


def test_set_display_inst_name_without_label(monkeypatch, runner):
    task = _fake_task(instances=[{"ip_addr": "1.2.3.4"}])
    monkeypatch.setattr(runner, "get_collect_inst", lambda: task)
    assert runner.set_display_inst_name({"host": "1.2.3.4"}) == "1.2.3.4"


def test_set_asso_instances(runner):
    out = runner.set_asso_instances({"self_device": "dev1"}, model_id="disk")
    assert out == [
        {
            "model_id": "host",
            "inst_name": "dev1",
            "asst_id": "contains",
            "model_asst_id": "host_contains_disk",
        }
    ]
