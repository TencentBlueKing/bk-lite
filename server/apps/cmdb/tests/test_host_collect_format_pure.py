# -*- coding: utf-8 -*-
"""HostCollectMetrics 采集解析端到端测试（format_data -> format_metrics）。

不连 DB/VM：model_id 桩为 "host"，喂真实形态的 VictoriaMetrics 指标 dict，
断言指标分流（host_proc 聚合 / 失败状态过滤 / 过期时间戳熔断）、字段映射
转换（int 转换 / MAC 规范化 / CPU 架构 / OS 类型 / 进程 JSON）后的真实输出。
"""
import pydantic.root_model  # noqa: F401  预热
import time

import pytest

from apps.cmdb.collection.collect_plugin.host import HostCollectMetrics


class _FakeTask:
    def __init__(self, instances=None, params=None):
        self.instances = instances if instances is not None else []
        self.params = params if params is not None else {}


@pytest.fixture
def runner(monkeypatch):
    monkeypatch.setattr(HostCollectMetrics, "model_id", property(lambda self: "host"))
    r = HostCollectMetrics("web01", "cmdb_1", 1)
    # set_cloud/set_display_inst_name 依赖 get_collect_inst()，桩为内存快照避免连 DB
    monkeypatch.setattr(
        r,
        "get_collect_inst",
        lambda: _FakeTask(
            instances=[{"ip_addr": "10.0.0.9", "cloud": "vpc-1", "cloud_name": "生产云"}],
            params={},
        ),
    )
    return r


def _now_ts():
    return int(time.time())


def _metric_row(name, value="1", **labels):
    metric = {"__name__": name, "collect_status": "success"}
    metric.update(labels)
    return {"metric": metric, "value": [_now_ts(), value]}


# ---------------------------------------------------------------------------
# format_data 分流
# ---------------------------------------------------------------------------


def test_format_data_non_dict_returns_none(runner):
    assert runner.format_data([]) is None
    assert runner.format_data({"no_result_key": 1}) is None


def test_format_data_collects_host_metric(runner):
    data = {"result": [_metric_row("host_info_gauge", hostname="h1")]}
    runner.format_data(data)
    assert len(runner.collection_metrics_dict["host_info_gauge"]) == 1
    row = runner.collection_metrics_dict["host_info_gauge"][0]
    assert row["index_key"] == "host_info_gauge"
    assert row["hostname"] == "h1"
    assert runner.timestamp_gt is True


def test_format_data_skips_failed_status(runner):
    row = _metric_row("host_info_gauge", hostname="h1")
    row["metric"]["collect_status"] = "failed"
    runner.format_data({"result": [row]})
    assert runner.collection_metrics_dict["host_info_gauge"] == []


def test_format_data_proc_metric_aggregates_not_appended(runner):
    proc_row = _metric_row(
        "host_proc_usage_info_gauge", ip_addr="10.0.0.1", pid="100", proc_name="nginx"
    )
    proc_row["metric"]["name"] = "nginx"
    runner.format_data({"result": [proc_row]})
    # host_proc 指标不进入 collection_metrics_dict，而是聚合到 host_proc_map
    assert runner.collection_metrics_dict["host_proc_usage_info_gauge"] == []
    assert runner.host_proc_map["10.0.0.1"][0]["name"] == "nginx"


def test_format_data_breaks_on_stale_timestamp(runner):
    stale = {
        "metric": {"__name__": "host_info_gauge", "collect_status": "success", "hostname": "h1"},
        "value": [_now_ts() - 3 * 24 * 3600, "1"],
    }
    runner.format_data({"result": [stale]})
    # 过期时间戳触发 break，未收集任何数据且 timestamp_gt 仍为 False
    assert runner.collection_metrics_dict["host_info_gauge"] == []
    assert runner.timestamp_gt is False


# ---------------------------------------------------------------------------
# format_metrics 字段映射端到端
# ---------------------------------------------------------------------------


def test_format_metrics_full_field_mapping(runner):
    runner.host_proc_map = {}
    index = {
        "index_key": "host_info_gauge",
        "hostname": "myhost",
        "os_type": "Linux",
        "os_name": "Ubuntu",
        "os_version": "22.04",
        "os_bits": "64",
        "cpu_model": "Intel",
        "cpu_cores": "8",
        "memory_gb": "16",
        "disk_gb": "500",
        "cpu_architecture": "x86_64",
        "mac_address": "AA-BB-CC-DD-EE-FF",
        "host": "10.0.0.9",
    }
    runner.collection_metrics_dict["host_info_gauge"] = [index]
    runner.format_metrics()

    result = runner.result["host"]
    assert len(result) == 1
    item = result[0]
    assert item["hostname"] == "myhost"
    assert item["ip_addr"] == "10.0.0.9"
    assert item["os_type"] == "1"  # Linux -> id 1
    assert item["cpu_core"] == 8  # transform_int
    assert item["memory"] == 16
    assert item["disk"] == 500
    assert item["cpu_arch"] == "x64"  # x86_64 -> x64
    assert item["inner_mac"] == "AA:BB:CC:DD:EE:FF"
    assert item["proc"] == "[]"  # 无聚合进程，get_host_proc 返回空列表 JSON
    assert item["cloud"] == "vpc-1"  # 来自快照 instance 的 cloud
    assert item["inst_name"] == "10.0.0.9[生产云]"  # ip[云标签]


def test_format_metrics_tuple_missing_field_defaults(runner):
    # cpu_cores 缺失 -> tuple 分支走 else，数值字段默认 0
    index = {"index_key": "host_info_gauge", "host": "10.0.0.2"}
    runner.collection_metrics_dict["host_info_gauge"] = [index]
    runner.format_metrics()
    item = runner.result["host"][0]
    assert item["cpu_core"] == 0
    assert item["memory"] == 0
    assert item["disk"] == 0
    assert item["os_name"] == ""  # 非数值字段缺失默认空串


def test_format_metrics_tuple_bad_value_caught(runner):
    # cpu_cores 为不可转换字符串 -> transform_int 抛 ValueError 被捕获，落 0
    index = {"index_key": "host_info_gauge", "host": "10.0.0.3", "cpu_cores": "abc"}
    runner.collection_metrics_dict["host_info_gauge"] = [index]
    runner.format_metrics()
    assert runner.result["host"][0]["cpu_core"] == 0


def test_format_metrics_skips_unmapped_model(runner):
    # 指标 key 对应的 model_id 无映射时跳过
    runner.collection_metrics_dict["unknown_xyz_info_gauge"] = [{"a": 1}]
    runner.format_metrics()
    assert "unknown_xyz" not in runner.result


# ---------------------------------------------------------------------------
# set_cpu_arch / set_serverarch_type 深度分支
# ---------------------------------------------------------------------------


def test_set_cpu_arch_empty_returns_other(runner):
    assert runner.set_cpu_arch({}) == "other"


def test_set_cpu_arch_x86_64_not_misclassified(runner):
    # x86_64 必须映射到 x64，不能被 "x86" 子串误判
    assert runner.set_cpu_arch({"cpu_architecture": "x86_64"}) == "x64"


def test_set_cpu_arch_aarch64(runner):
    assert runner.set_cpu_arch({"cpu_architecture": "aarch64"}) == "arm64"


def test_set_cpu_arch_unknown_returns_other(runner):
    assert runner.set_cpu_arch({"cpu_architecture": "sparc"}) == "other"


def test_set_serverarch_type_branches(runner):
    assert runner.set_serverarch_type({}) == "other"
    assert runner.set_serverarch_type({"cpu_arch": "arm64"}) == "arm64"
    assert runner.set_serverarch_type({"cpu_arch": "weird"}) == "other"
