# -- coding: utf-8 --
"""IPAM 发现采集任务参数与旧 NATS 链路防回归测试。"""
from types import SimpleNamespace

import pytest

from apps.cmdb.constants.constants import CollectInputMethod
from apps.cmdb.services.ipam_discovery import extract_subnet_discovery_params

pytestmark = pytest.mark.unit


def _make_task(instances=None, params=None):
    return SimpleNamespace(
        id=1,
        input_method=CollectInputMethod.SUBNET,
        instances=instances if instances is not None else {},
        params=params if params is not None else {},
    )


class TestExtractSubnetDiscoveryParams:
    def test_从params提取subnet_ids(self):
        task = _make_task(params={"subnet_ids": [1, 2, 3], "scan_method": "tcp", "ports": [22, 80]})
        subnet_ids, scan_method, ports = extract_subnet_discovery_params(task)
        assert subnet_ids == [1, 2, 3]
        assert scan_method == "tcp"
        assert ports == [22, 80]

    def test_从历史instances提取subnet_ids(self):
        task = _make_task(instances={"subnet_ids": [5], "scan_method": "icmp", "ports": None})
        subnet_ids, scan_method, ports = extract_subnet_discovery_params(task)
        assert subnet_ids == [5]
        assert scan_method == "icmp"
        assert ports is None

    def test_params优先于instances(self):
        task = _make_task(
            instances={"subnet_ids": [1], "scan_method": "icmp"},
            params={"subnet_ids": [2], "scan_method": "tcp", "ports": [443]},
        )
        subnet_ids, scan_method, ports = extract_subnet_discovery_params(task)
        assert subnet_ids == [2]
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
