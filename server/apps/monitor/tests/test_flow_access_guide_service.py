"""FlowAccessGuideService 测试 — 监听端点拼接/接入文档构建,NodeMgmt 与 DB 走真实边界 mock。"""
from unittest.mock import patch

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException, ValidationAppException
from apps.monitor.models import MonitorObject
from apps.monitor.services.flow_access_guide import FlowAccessGuideService as Svc

pytestmark = pytest.mark.unit


def _patch_nodemgmt(env_config):
    return patch(
        "apps.monitor.services.flow_access_guide.NodeMgmt",
        return_value=type("M", (), {"get_cloud_region_envconfig": lambda self, _id: env_config})(),
    )


def test_get_listener_endpoint_netflow():
    with _patch_nodemgmt({"NODE_SERVER_URL": "http://10.0.0.5:8080"}):
        ep = Svc.get_listener_endpoint("netflow", 1)
    assert ep == "udp://10.0.0.5:2056"


def test_get_listener_endpoint_sflow():
    with _patch_nodemgmt({"NODE_SERVER_URL": "https://host.local"}):
        ep = Svc.get_listener_endpoint("sflow", 1)
    assert ep == "udp://host.local:6343"


def test_invalid_protocol_raises():
    with pytest.raises(BaseAppException):
        Svc.get_listener_endpoint("bogus", 1)


def test_listener_host_non_dict_envconfig_raises():
    with _patch_nodemgmt(None):
        with pytest.raises(BaseAppException, match="获取云区域环境变量失败"):
            Svc.get_listener_endpoint("netflow", 1)


def test_listener_host_missing_url_raises():
    with _patch_nodemgmt({"OTHER": "x"}):
        with pytest.raises(BaseAppException, match="未配置 NODE_SERVER_URL"):
            Svc.get_listener_endpoint("netflow", 1)


def test_listener_host_invalid_url_raises():
    with _patch_nodemgmt({"NODE_SERVER_URL": "no-scheme-host"}):
        with pytest.raises(BaseAppException, match="配置不合法"):
            Svc.get_listener_endpoint("netflow", 1)


def test_listener_host_ipv6_bracketed():
    with _patch_nodemgmt({"NODE_SERVER_URL": "http://[fe80::1]:8080"}):
        ep = Svc.get_listener_endpoint("sflow", 1)
    assert ep == "udp://[fe80::1]:6343"


def test_get_listener_endpoints_netflow_two_versions():
    with _patch_nodemgmt({"NODE_SERVER_URL": "http://h"}):
        eps = Svc.get_listener_endpoints("netflow", 1)
    ports = {e["port"] for e in eps}
    assert ports == {2055, 2056}
    assert {e["protocol"] for e in eps} == {"netflow_v5", "netflow_v9"}
    assert eps[0]["endpoint"] == "udp://h:2055"


def test_get_listener_endpoints_sflow_single():
    with _patch_nodemgmt({"NODE_SERVER_URL": "http://h"}):
        eps = Svc.get_listener_endpoints("sflow", 1)
    assert len(eps) == 1
    assert eps[0]["port"] == 6343


@pytest.mark.django_db
def test_build_document_uses_display_name_and_netflow_tip():
    obj = MonitorObject.objects.create(name="Switch", level="base", display_name="交换机")
    with _patch_nodemgmt({"NODE_SERVER_URL": "http://h"}):
        doc = Svc.build_document(protocol="netflow", cloud_region_id=1, monitor_object=obj)
    assert doc["protocol_name"] == "NetFlow"
    assert doc["monitor_object_name"] == "交换机"
    assert doc["endpoint"] == "udp://h:2056"
    assert any("2055" in s for s in doc["instructions"])
    assert len(doc["listener_endpoints"]) == 2


@pytest.mark.django_db
def test_build_document_resolves_object_by_id_and_falls_back_to_name():
    obj = MonitorObject.objects.create(name="Router", level="base", display_name="")
    with _patch_nodemgmt({"NODE_SERVER_URL": "http://h"}):
        doc = Svc.build_document(protocol="sflow", cloud_region_id=2, monitor_object_id=obj.id)
    assert doc["protocol_name"] == "sFlow"
    assert doc["monitor_object_name"] == "Router"


@pytest.mark.django_db
def test_resolve_monitor_object_missing_id_raises():
    with pytest.raises(ValidationAppException, match="does not exist"):
        Svc._resolve_monitor_object(monitor_object=None, monitor_object_id=None)


@pytest.mark.django_db
def test_resolve_monitor_object_unsupported_name_raises():
    obj = MonitorObject.objects.create(name="Host", level="base")
    with pytest.raises(ValidationAppException, match="Unsupported flow monitor object"):
        Svc._resolve_monitor_object(monitor_object=obj)
