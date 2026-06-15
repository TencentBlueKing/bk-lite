# -*- coding: utf-8 -*-
"""FusionInsight 采集器单测：不真连 HTTP，mock list_* / 喂原始 API item 给 _map_* 纯函数，
断言输出业务字段集合恰好对齐模型 attr 表，并校验隐藏关联字段 cluster_id。

设计要点：FusionInsight 平台对象无可采集业务字段，故采集器不输出平台对象，
只输出 fusioninsight_cluster / fusioninsight_host 两类。
"""
import sys
from pathlib import Path
from unittest.mock import patch

STARGAZER_ROOT = Path(__file__).resolve().parents[1]
if str(STARGAZER_ROOT) not in sys.path:
    sys.path.insert(0, str(STARGAZER_ROOT))


# ----------------------------------------------------------------------------
# 原始 API item（移植自 old cw_fusioninsight 的 list_* 字段过滤结果）
# list_clusters: ["id", "name"]
# list_hosts: ["hostname","ip","cpuCores","totalMemory","totalHardDiskSpace",
#              "runningStatus","osType","clusterName","clusterId"]
# ----------------------------------------------------------------------------
RAW_CLUSTER = {
    "id": 1,  # 数字 id，需转 str
    "name": "cluster-a",
}

RAW_HOST = {
    "hostname": "host-a",
    "ip": "10.0.0.11",
    "cpuCores": 32,
    "totalMemory": 65536,
    "totalHardDiskSpace": 2048,
    "runningStatus": "normal",
    "osType": "EulerOS",
    "clusterName": "cluster-a",
    "clusterId": 1,  # 数字 id，需转 str 与 cluster.resource_id 对齐
}


def _make_manager():
    from plugins.inputs.fusioninsight.fusioninsight_info import FusionInsightManager

    return FusionInsightManager(
        params={
            "username": "admin",
            "password": "secret",
            "region": "RegionOne",
            "host": "10.0.0.1",
        }
    )


# ----------------------------------------------------------------------------
# 纯函数字段重命名测试
# ----------------------------------------------------------------------------
def test_map_cluster_fields():
    mgr = _make_manager()
    out = mgr._map_cluster(RAW_CLUSTER)
    assert set(out.keys()) == {"resource_name", "resource_id"}
    assert out["resource_name"] == "cluster-a"
    assert out["resource_id"] == "1"  # str(id)，即使是数字也转 str
    assert isinstance(out["resource_id"], str)


def test_map_host_fields():
    mgr = _make_manager()
    out = mgr._map_host(RAW_HOST)
    business_keys = {
        "resource_name", "resource_id", "ip_addr", "vcpus", "memory_mb",
        "storage_gb", "status", "os_name",
    }
    # 隐藏字段 cluster_id 用于 host belong cluster
    assert (set(out.keys()) - business_keys) == {"cluster_id"}
    assert out["resource_name"] == "host-a"
    assert out["resource_id"] == "host-a"  # = hostname
    assert out["ip_addr"] == "10.0.0.11"
    assert out["vcpus"] == "32"
    assert out["memory_mb"] == "65536"
    assert out["storage_gb"] == "2048"
    assert out["status"] == "normal"
    assert out["os_name"] == "EulerOS"
    assert out["cluster_id"] == "1"  # str(clusterId)，与 cluster.resource_id 同为 str
    assert isinstance(out["cluster_id"], str)


def test_map_host_none_cpu_cores_is_empty():
    """cpuCores 为 None 时 vcpus 应为空串而非字符串 'None'。"""
    mgr = _make_manager()
    raw = dict(RAW_HOST, cpuCores=None)
    out = mgr._map_host(raw)
    assert out["vcpus"] == ""


def test_map_host_none_int_fields_are_empty():
    mgr = _make_manager()
    raw = dict(RAW_HOST, totalMemory=None, totalHardDiskSpace=None)
    out = mgr._map_host(raw)
    assert out["memory_mb"] == ""
    assert out["storage_gb"] == ""


# ----------------------------------------------------------------------------
# get_* 聚合测试（mock list_* 返回原始 data）
# ----------------------------------------------------------------------------
def test_get_clusters_via_mock_list():
    mgr = _make_manager()
    with patch.object(mgr, "list_clusters", return_value={"result": True, "data": [RAW_CLUSTER]}):
        clusters = mgr.get_clusters()
    assert len(clusters) == 1
    assert clusters[0]["resource_name"] == "cluster-a"
    assert clusters[0]["resource_id"] == "1"


def test_get_hosts_via_mock_list():
    mgr = _make_manager()
    with patch.object(mgr, "list_hosts", return_value={"result": True, "data": [RAW_HOST]}):
        hosts = mgr.get_hosts()
    assert len(hosts) == 1
    assert hosts[0]["resource_id"] == "host-a"
    assert hosts[0]["cluster_id"] == "1"


def test_no_get_platform():
    """FusionInsight 平台无业务字段，采集器不应实现 get_platform。"""
    mgr = _make_manager()
    assert not hasattr(mgr, "get_platform")


# ----------------------------------------------------------------------------
# list_all_resources 聚合 + 错误兜底
# ----------------------------------------------------------------------------
def test_list_all_resources_success():
    mgr = _make_manager()
    with patch.object(mgr, "get_clusters", return_value=[mgr._map_cluster(RAW_CLUSTER)]), \
            patch.object(mgr, "get_hosts", return_value=[mgr._map_host(RAW_HOST)]):
        out = mgr.list_all_resources()

    assert out["success"] is True
    result = out["result"]
    # 只含 cluster/host 两键，无 fusioninsight 平台键
    assert set(result.keys()) == {"fusioninsight_cluster", "fusioninsight_host"}
    assert "fusioninsight" not in result
    assert result["fusioninsight_cluster"][0]["resource_name"] == "cluster-a"
    assert result["fusioninsight_host"][0]["cluster_id"] == "1"


def test_list_all_resources_error_branch():
    mgr = _make_manager()
    with patch.object(mgr, "get_clusters", side_effect=RuntimeError("boom")):
        out = mgr.list_all_resources()
    assert out["success"] is False
    assert "cmdb_collect_error" in out["result"]


def test_missing_requests_reports_clear_error(monkeypatch):
    """requests 未安装时应返回清晰错误而非崩溃。"""
    from plugins.inputs.fusioninsight import fusioninsight_info
    monkeypatch.setattr(fusioninsight_info, "requests", None)
    mgr = fusioninsight_info.FusionInsightManager(params={
        "username": "u", "password": "p", "region": "r",
        "host": "fi.example.com",
    })
    out = mgr.list_all_resources()
    assert out["success"] is False
    assert "requests" in out["result"]["cmdb_collect_error"]
