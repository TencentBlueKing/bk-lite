"""云区域 Stargazer / NATS Executor 健康检查：只 mock RPC 客户端。"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.node_mgmt.constants.cloudregion_service import CloudRegionServiceConstants
from apps.node_mgmt.tasks.services import cloud_service_check_health as health

pytestmark = pytest.mark.unit


@pytest.fixture
def region():
    return SimpleNamespace(name="zone-a")


def test_check_stargazer_health_ok(monkeypatch, region):
    monkeypatch.setattr(health.RegionService, "get_region_service_instance_id", staticmethod(lambda *a: "inst-1"))
    client = MagicMock()
    client.health_check.return_value = {"status": "ok"}
    monkeypatch.setattr(health, "Stargazer", lambda instance_id: client)
    status, message = health.check_stargazer_health(region)
    assert status == CloudRegionServiceConstants.NORMAL
    assert message == "服务正常"
    client.health_check.assert_called_once_with(timeout=health.HEALTH_CHECK_TIMEOUT)


def test_check_stargazer_health_abnormal_payload(monkeypatch, region):
    monkeypatch.setattr(health.RegionService, "get_region_service_instance_id", staticmethod(lambda *a: "inst-1"))
    client = MagicMock()
    client.health_check.return_value = {"status": "down"}
    monkeypatch.setattr(health, "Stargazer", lambda instance_id: client)
    status, message = health.check_stargazer_health(region)
    assert status == CloudRegionServiceConstants.N_ERROR
    assert "异常" in message


def test_check_stargazer_health_exception(monkeypatch, region):
    monkeypatch.setattr(health.RegionService, "get_region_service_instance_id", staticmethod(lambda *a: "inst-1"))
    monkeypatch.setattr(health, "Stargazer", lambda instance_id: (_ for _ in ()).throw(RuntimeError("rpc down")))
    status, message = health.check_stargazer_health(region)
    assert status == CloudRegionServiceConstants.N_ERROR
    assert "rpc down" in message


def test_check_nats_executor_health_ok_and_failure(monkeypatch, region):
    monkeypatch.setattr(health.RegionService, "get_region_service_instance_id", staticmethod(lambda *a: "exec-1"))
    client = MagicMock()
    client.health_check.return_value = {"status": "ok"}
    monkeypatch.setattr(health, "Executor", lambda instance_id: client)
    status, message = health.check_nats_executor_health(region)
    assert status == CloudRegionServiceConstants.NORMAL
    assert message == "服务正常"

    client.health_check.return_value = None
    status, message = health.check_nats_executor_health(region)
    assert status == CloudRegionServiceConstants.N_ERROR

    monkeypatch.setattr(health, "Executor", lambda instance_id: (_ for _ in ()).throw(TimeoutError("timeout")))
    status, message = health.check_nats_executor_health(region)
    assert status == CloudRegionServiceConstants.N_ERROR
    assert "timeout" in message


def test_services_func_maps_known_service_names():
    assert health.SERVICES_FUNC[CloudRegionServiceConstants.STARGAZER_SERVICE_NAME] is health.check_stargazer_health
    assert health.SERVICES_FUNC[CloudRegionServiceConstants.NATS_EXECUTOR_SERVICE_NAME] is health.check_nats_executor_health
