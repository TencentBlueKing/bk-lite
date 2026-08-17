# -*- coding: utf-8 -*-
"""FusionInsight 采集器单测：不真连 HTTP，mock list_* / 喂原始 API item 给 _map_* 纯函数，
断言输出业务字段集合恰好对齐模型 attr 表，并校验隐藏关联字段 cluster_id。

设计要点：FusionInsight 平台对象无可采集业务字段，故采集器不输出平台对象，
只输出 fusioninsight_cluster / fusioninsight_host 两类。
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

STARGAZER_ROOT = Path(__file__).resolve().parents[1]
if str(STARGAZER_ROOT) not in sys.path:
    sys.path.insert(0, str(STARGAZER_ROOT))


RAW_CLUSTER = {
    "id": 1,
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
    "clusterId": 1,
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


def test_map_cluster_fields():
    mgr = _make_manager()
    out = mgr._map_cluster(RAW_CLUSTER)
    assert set(out.keys()) == {"resource_name", "resource_id"}
    assert out["resource_name"] == "cluster-a"
    assert out["resource_id"] == "1"
    assert isinstance(out["resource_id"], str)


def test_map_host_fields():
    mgr = _make_manager()
    out = mgr._map_host(RAW_HOST)
    business_keys = {
        "resource_name", "resource_id", "ip_addr", "vcpus", "memory_mb",
        "storage_gb", "status", "os_name",
    }
    assert (set(out.keys()) - business_keys) == {"cluster_id"}
    assert out["resource_name"] == "host-a"
    assert out["resource_id"] == "host-a"
    assert out["ip_addr"] == "10.0.0.11"
    assert out["vcpus"] == "32"
    assert out["memory_mb"] == "65536"
    assert out["storage_gb"] == "2048"
    assert out["status"] == "normal"
    assert out["os_name"] == "EulerOS"
    assert out["cluster_id"] == "1"
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


@pytest.mark.asyncio
async def test_get_clusters_via_mock_list():
    mgr = _make_manager()
    with patch.object(
        mgr,
        "list_clusters",
        new_callable=AsyncMock,
        return_value={"result": True, "data": [RAW_CLUSTER]},
    ):
        clusters = await mgr.get_clusters()
    assert len(clusters) == 1
    assert clusters[0]["resource_name"] == "cluster-a"
    assert clusters[0]["resource_id"] == "1"


@pytest.mark.asyncio
async def test_get_hosts_via_mock_list():
    mgr = _make_manager()
    with patch.object(
        mgr,
        "list_hosts",
        new_callable=AsyncMock,
        return_value={"result": True, "data": [RAW_HOST]},
    ):
        hosts = await mgr.get_hosts()
    assert len(hosts) == 1
    assert hosts[0]["resource_id"] == "host-a"
    assert hosts[0]["cluster_id"] == "1"


def test_no_get_platform():
    """FusionInsight 平台无业务字段，采集器不应实现 get_platform。"""
    mgr = _make_manager()
    assert not hasattr(mgr, "get_platform")


@pytest.mark.asyncio
async def test_list_all_resources_success():
    mgr = _make_manager()
    with patch.object(
        mgr,
        "get_clusters",
        new_callable=AsyncMock,
        return_value=[mgr._map_cluster(RAW_CLUSTER)],
    ), patch.object(
        mgr,
        "get_hosts",
        new_callable=AsyncMock,
        return_value=[mgr._map_host(RAW_HOST)],
    ):
        out = await mgr.list_all_resources()

    assert out["success"] is True
    result = out["result"]
    assert set(result.keys()) == {"fusioninsight_cluster", "fusioninsight_host"}
    assert "fusioninsight" not in result
    assert result["fusioninsight_cluster"][0]["resource_name"] == "cluster-a"
    assert result["fusioninsight_host"][0]["cluster_id"] == "1"


@pytest.mark.asyncio
async def test_list_all_resources_error_branch():
    mgr = _make_manager()
    with patch.object(
        mgr, "get_clusters", new_callable=AsyncMock, side_effect=RuntimeError("boom")
    ):
        out = await mgr.list_all_resources()
    assert out["success"] is False
    assert "cmdb_collect_error" in out["result"]


@pytest.mark.asyncio
async def test_httpx_request_failure_reports_clear_error(monkeypatch):
    """httpx 请求失败时应返回清晰错误而非崩溃。"""
    from plugins.inputs.fusioninsight import fusioninsight_info

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def request(self, *_args, **_kwargs):
            raise httpx.ConnectError("connection refused")

        async def aclose(self):
            return None

    monkeypatch.setattr(fusioninsight_info.httpx, "AsyncClient", FakeAsyncClient)
    mgr = fusioninsight_info.FusionInsightManager(
        params={
            "username": "u",
            "password": "p",
            "region": "r",
            "host": "fi.example.com",
        }
    )
    out = await mgr.list_all_resources()
    assert out["success"] is False
    assert "cmdb_collect_error" in out["result"]


@pytest.mark.asyncio
async def test_https_port_and_certificate_verification_are_honored(monkeypatch):
    from plugins.inputs.fusioninsight import fusioninsight_info

    client_kwargs = []
    calls = []

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            client_kwargs.append(kwargs)

        async def aclose(self):
            return None

    async def fake_handle_request(method, url, client=None, **kwargs):
        calls.append((method, url, kwargs))
        return {"result": True, "data": {}}

    monkeypatch.setattr(fusioninsight_info.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(fusioninsight_info, "handle_request", fake_handle_request)

    mgr = fusioninsight_info.FusionInsightManager(
        {
            "username": "u",
            "password": "p",
            "host": "fi.example.com",
            "port": 9443,
            "verify_tls": False,
        }
    )

    await mgr.login()

    assert mgr.basic_url == "https://fi.example.com:9443/web"
    assert client_kwargs[0]["verify"] is False
    assert calls[0][0] == "GET"
    assert calls[0][1].endswith("/api/v2/session/status")
