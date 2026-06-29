# -- coding: utf-8 --
"""TDD：选子网 IP 发现任务路由（§13 工作项 2）。

覆盖范围：
  - maybe_dispatch_ip_discovery 的路由决策（纯逻辑，mock Stargazer.dispatch_ip_discovery）
  - extract_subnet_discovery_params 的参数提取（纯逻辑，无 IO）
  - 非 IP 任务不触发 IP 发现路径

未覆盖（TODO 2.7，e2e 不可离线验证）：
  - sync_collect_task Celery 任务完整执行（需 Django + DB + Celery）
  - Stargazer NATS publish（需运行时 NATS broker）
  - apply_discovery_result 回写（已在 test_ipam_discovery_service.py 覆盖）
"""
import pytest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from apps.cmdb.services.ipam_discovery import (
    extract_subnet_discovery_params,
    maybe_dispatch_ip_discovery,
)
from apps.cmdb.constants.constants import CollectInputMethod, CollectPluginTypes

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 辅助：构造最小化 task 对象（不依赖 Django ORM）
# ---------------------------------------------------------------------------

def _make_task(task_type=CollectPluginTypes.IP, input_method=CollectInputMethod.SUBNET, instances=None):
    """返回一个鸭子类型任务对象（SimpleNamespace），模拟 CollectModels 实例。"""
    return SimpleNamespace(
        id=1,
        task_type=task_type,
        input_method=input_method,
        instances=instances if instances is not None else {
            "subnet_ids": [10, 20],
            "scan_method": "icmp",
            "ports": None,
        },
    )


# ---------------------------------------------------------------------------
# extract_subnet_discovery_params 参数提取
# ---------------------------------------------------------------------------

class TestExtractSubnetDiscoveryParams:
    def test_从model实例提取subnet_ids(self):
        task = _make_task(instances={"subnet_ids": [1, 2, 3], "scan_method": "tcp", "ports": [22, 80]})
        subnet_ids, scan_method, ports = extract_subnet_discovery_params(task)
        assert subnet_ids == [1, 2, 3]
        assert scan_method == "tcp"
        assert ports == [22, 80]

    def test_从dict提取subnet_ids(self):
        task_dict = {
            "task_type": CollectPluginTypes.IP,
            "input_method": CollectInputMethod.SUBNET,
            "instances": {"subnet_ids": [5], "scan_method": "icmp", "ports": None},
        }
        subnet_ids, scan_method, ports = extract_subnet_discovery_params(task_dict)
        assert subnet_ids == [5]
        assert scan_method == "icmp"
        assert ports is None

    def test_instances为空dict时返回空列表和默认值(self):
        task = _make_task(instances={})
        subnet_ids, scan_method, ports = extract_subnet_discovery_params(task)
        assert subnet_ids == []
        assert scan_method == "icmp"
        assert ports is None

    def test_instances为list时安全降级(self):
        # instances 字段存储了非预期的 list（如普通采集任务），应安全降级
        task = _make_task(instances=[{"host": "10.0.0.1"}])
        subnet_ids, scan_method, ports = extract_subnet_discovery_params(task)
        assert subnet_ids == []

    def test_scan_method缺省时默认icmp(self):
        task = _make_task(instances={"subnet_ids": [1]})
        _, scan_method, _ = extract_subnet_discovery_params(task)
        assert scan_method == "icmp"

    def test_scan_method为空字符串时默认icmp(self):
        task = _make_task(instances={"subnet_ids": [1], "scan_method": ""})
        _, scan_method, _ = extract_subnet_discovery_params(task)
        assert scan_method == "icmp"


# ---------------------------------------------------------------------------
# maybe_dispatch_ip_discovery 路由决策
# ---------------------------------------------------------------------------

class TestMaybeDispatchIpDiscovery:
    """
    Stargazer はマっ maybe_dispatch_ip_discovery 内で lazy import されているため、
    patch ターゲットは `apps.rpc.stargazer.Stargazer`（クラス定義元）を指定する。
    """

    _PATCH_TARGET = "apps.rpc.stargazer.Stargazer"

    def test_ip加subnet任务调用dispatch并返回True(self):
        task = _make_task(
            task_type=CollectPluginTypes.IP,
            input_method=CollectInputMethod.SUBNET,
            instances={"subnet_ids": [10, 20], "scan_method": "icmp", "ports": None},
        )
        with patch(self._PATCH_TARGET) as MockStargazer:
            mock_instance = MagicMock()
            MockStargazer.return_value = mock_instance
            result = maybe_dispatch_ip_discovery(task)

        assert result is True
        MockStargazer.assert_called_once_with()
        mock_instance.dispatch_ip_discovery.assert_called_once_with(
            subnet_ids=[10, 20],
            scan_method="icmp",
            ports=None,
        )

    def test_ip加subnet任务传递自定义ports(self):
        task = _make_task(
            task_type=CollectPluginTypes.IP,
            input_method=CollectInputMethod.SUBNET,
            instances={"subnet_ids": [7], "scan_method": "tcp", "ports": [22, 8080]},
        )
        with patch(self._PATCH_TARGET) as MockStargazer:
            mock_instance = MagicMock()
            MockStargazer.return_value = mock_instance
            maybe_dispatch_ip_discovery(task)

        mock_instance.dispatch_ip_discovery.assert_called_once_with(
            subnet_ids=[7],
            scan_method="tcp",
            ports=[22, 8080],
        )

    def test_非IP任务不触发dispatch并返回False(self):
        """HOST/PROTOCOL/SNMP 等其他 task_type 不应路由到 IP 发现。"""
        for task_type in [
            CollectPluginTypes.HOST,
            CollectPluginTypes.PROTOCOL,
            CollectPluginTypes.SNMP,
            CollectPluginTypes.CLOUD,
            CollectPluginTypes.DB,
        ]:
            task = _make_task(
                task_type=task_type,
                input_method=CollectInputMethod.SUBNET,
                instances={"subnet_ids": [1]},
            )
            with patch(self._PATCH_TARGET) as MockStargazer:
                result = maybe_dispatch_ip_discovery(task)
            assert result is False, f"task_type={task_type} 不应触发 IP 发现"
            MockStargazer.assert_not_called()

    def test_IP任务但input_method为AUTO不触发dispatch(self):
        """task_type=ip 但 input_method != SUBNET，走常规采集路径。"""
        task = _make_task(
            task_type=CollectPluginTypes.IP,
            input_method=CollectInputMethod.AUTO,
            instances={"subnet_ids": [1]},
        )
        with patch(self._PATCH_TARGET) as MockStargazer:
            result = maybe_dispatch_ip_discovery(task)
        assert result is False
        MockStargazer.assert_not_called()

    def test_IP任务但input_method为MANUAL不触发dispatch(self):
        task = _make_task(
            task_type=CollectPluginTypes.IP,
            input_method=CollectInputMethod.MANUAL,
            instances={"subnet_ids": [1]},
        )
        with patch(self._PATCH_TARGET) as MockStargazer:
            result = maybe_dispatch_ip_discovery(task)
        assert result is False
        MockStargazer.assert_not_called()

    def test_subnet_ids为空时不触发dispatch并返回False(self):
        """subnet_ids 空列表：无需下发，返回 False 避免空操作。"""
        task = _make_task(
            task_type=CollectPluginTypes.IP,
            input_method=CollectInputMethod.SUBNET,
            instances={"subnet_ids": [], "scan_method": "icmp"},
        )
        with patch(self._PATCH_TARGET) as MockStargazer:
            result = maybe_dispatch_ip_discovery(task)
        assert result is False
        MockStargazer.assert_not_called()

    def test_从dict形式任务路由(self):
        """maybe_dispatch_ip_discovery 接受纯 dict（序列化后的任务表示）。"""
        task_dict = {
            "task_type": CollectPluginTypes.IP,
            "input_method": CollectInputMethod.SUBNET,
            "instances": {"subnet_ids": [3, 4], "scan_method": "icmp", "ports": None},
        }
        with patch(self._PATCH_TARGET) as MockStargazer:
            mock_instance = MagicMock()
            MockStargazer.return_value = mock_instance
            result = maybe_dispatch_ip_discovery(task_dict)
        assert result is True
        mock_instance.dispatch_ip_discovery.assert_called_once_with(
            subnet_ids=[3, 4],
            scan_method="icmp",
            ports=None,
        )


# ---------------------------------------------------------------------------
# CollectInputMethod 常量验证
# ---------------------------------------------------------------------------

class TestCollectInputMethodConstant:
    def test_SUBNET常量存在且值为2(self):
        assert hasattr(CollectInputMethod, "SUBNET")
        assert CollectInputMethod.SUBNET == 2

    def test_SUBNET在CHOICE中(self):
        choice_values = [v for v, _ in CollectInputMethod.CHOICE]
        assert CollectInputMethod.SUBNET in choice_values

    def test_AUTO和MANUAL未被破坏(self):
        assert CollectInputMethod.AUTO == 0
        assert CollectInputMethod.MANUAL == 1
