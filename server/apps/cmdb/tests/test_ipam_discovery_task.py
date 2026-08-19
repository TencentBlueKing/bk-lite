# -- coding: utf-8 --
"""IPAM 发现采集任务参数与旧 NATS 链路防回归测试。"""
from types import SimpleNamespace

import pytest

from apps.cmdb.constants.constants import CollectInputMethod
from apps.cmdb.services.ipam_discovery import extract_subnet_discovery_params

SUBNET_UUID_1 = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
SUBNET_UUID_2 = "8fe27a46-1fc0-41df-8db4-8d817e164291"
SUBNET_UUID_3 = "d2555d42-4085-4c57-8686-935ea64dd959"

pytestmark = pytest.mark.unit


def _make_task(instances=None, params=None):
    return SimpleNamespace(
        id=1,
        input_method=CollectInputMethod.SUBNET,
        instances=instances if instances is not None else {},
        params=params if params is not None else {},
    )


class TestExtractSubnetDiscoveryParams:
    def test_从params提取subnet_uuids(self):
        task = _make_task(params={"subnet_uuids": [SUBNET_UUID_1, SUBNET_UUID_2], "scan_method": "tcp", "ports": [22, 80]})
        subnet_ids, scan_method, ports = extract_subnet_discovery_params(task)
        assert subnet_ids == [SUBNET_UUID_1, SUBNET_UUID_2]
        assert scan_method == "tcp"
        assert ports == [22, 80]

    def test_从instances提取subnet_uuids(self):
        task = _make_task(instances={"subnet_uuids": [SUBNET_UUID_3], "scan_method": "icmp", "ports": None})
        subnet_ids, scan_method, ports = extract_subnet_discovery_params(task)
        assert subnet_ids == [SUBNET_UUID_3]
        assert scan_method == "icmp"
        assert ports is None

    def test_存量subnet_ids仅供后端内部只读映射(self):
        task = _make_task(instances={"subnet_ids": [5], "scan_method": "icmp"})
        subnet_refs, scan_method, _ = extract_subnet_discovery_params(task)
        assert subnet_refs == [5]
        assert scan_method == "icmp"

    def test_params优先于instances(self):
        task = _make_task(
            instances={"subnet_uuids": [SUBNET_UUID_1], "scan_method": "icmp"},
            params={"subnet_uuids": [SUBNET_UUID_2], "scan_method": "tcp", "ports": [443]},
        )
        subnet_ids, scan_method, ports = extract_subnet_discovery_params(task)
        assert subnet_ids == [SUBNET_UUID_2]
        assert scan_method == "tcp"
        assert ports == [443]

    def test_空参数返回默认值(self):
        subnet_ids, scan_method, ports = extract_subnet_discovery_params(_make_task())
        assert subnet_ids == []
        assert scan_method == "icmp"
        assert ports is None

    def test_非法instances安全降级(self):
        subnet_ids, scan_method, ports = extract_subnet_discovery_params(_make_task(instances=[{"ip": "10.0.0.1"}]))
        assert subnet_ids == []
        assert scan_method == "icmp"
        assert ports is None


def test_旧nats_dispatch入口已删除():
    import apps.cmdb.services.ipam_discovery as ipam_discovery
    from apps.rpc.stargazer import Stargazer

    assert not hasattr(ipam_discovery, "maybe_dispatch_ip_discovery")
    assert not hasattr(ipam_discovery, "build_scan_payload")
    assert not hasattr(Stargazer, "dispatch_ip_discovery")
