# -*- coding: utf-8 -*-
"""PC 采集任务序列化校验合同测试。

锁定 validate_pc_collect_task：
- OS 归一化与固定 task/driver 类型；
- Windows 端口/协议组合与 NTLM 固定值、HTTP 安全提示；
- macOS 凭据互斥（密码 XOR 私钥）；
- 超时边界 30~300；
- 编辑时 OS 不可变；
- 非 PC 任务行为不变。
"""
from types import SimpleNamespace

import pytest

from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.serializers.collect_serializer import CollectModelSerializer


@pytest.fixture(autouse=True)
def _stub_auth_serializer_dependencies(monkeypatch):
    class _UserQuery:
        @staticmethod
        def values(*args):
            return []

    class _UserManager:
        @staticmethod
        def all():
            return _UserQuery()

    monkeypatch.setattr("apps.core.utils.serializers.User.objects", _UserManager())
    monkeypatch.setattr("apps.core.utils.serializers.get_permission_rules", lambda *args, **kwargs: {})
    monkeypatch.setattr(CollectModelSerializer.Meta, "validators", [], raising=False)


def _payload(params, credential, timeout=120, model_id="pc"):
    return {
        "name": "pc-discovery",
        "task_type": CollectPluginTypes.HOST,
        "driver_type": CollectDriverTypes.JOB,
        "model_id": model_id,
        "access_point": [{"id": 1}],
        "instances": [],
        "ip_range": "192.168.1.0/24",
        "cycle_value_type": "interval",
        "cycle_value": "60",
        "scan_cycle": "60",
        "timeout": timeout,
        "team": [1],
        "params": params,
        "credential": credential,
    }


def _serializer(payload, instance=None):
    request = SimpleNamespace(user=SimpleNamespace(group_list=[]), COOKIES={})
    if instance is not None:
        return CollectModelSerializer(instance, data=payload, partial=True, context={"request": request})
    return CollectModelSerializer(data=payload, context={"request": request})


WINDOWS_CREDENTIAL = [{"username": "ACME\\alice", "password": "secret", "port": 5986}]


def test_pc_windows_task_normalized_with_defaults():
    serializer = _serializer(_payload({"os_type": "windows"}, WINDOWS_CREDENTIAL))
    assert serializer.is_valid(), serializer.errors
    params = serializer.validated_data["params"]
    assert params["os_type"] == "windows"
    assert params["winrm_scheme"] == "https"
    assert params["winrm_transport"] == "ntlm"
    assert params["winrm_cert_validation"] is False
    assert "security_warning" not in params
    assert serializer.validated_data["driver_type"] == CollectDriverTypes.JOB


def test_pc_windows_explicit_http_5985_sets_security_warning():
    credential = [{"username": "alice", "password": "secret", "port": 5985}]
    serializer = _serializer(_payload({"os_type": "windows", "winrm_scheme": "http"}, credential))
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["params"]["security_warning"] == "WINRM_HTTP_INSECURE"


@pytest.mark.parametrize("port,scheme", [(5985, "https"), (5986, "http"), (22, "https")])
def test_pc_windows_rejects_port_scheme_mismatch(port, scheme):
    credential = [{"username": "alice", "password": "secret", "port": port}]
    serializer = _serializer(_payload({"os_type": "windows", "winrm_scheme": scheme}, credential))
    assert serializer.is_valid() is False


def test_pc_rejects_invalid_os_type():
    serializer = _serializer(_payload({"os_type": "linux"}, WINDOWS_CREDENTIAL))
    assert serializer.is_valid() is False
    assert "操作系统" in str(serializer.errors)


def test_pc_rejects_missing_os_type():
    serializer = _serializer(_payload({}, WINDOWS_CREDENTIAL))
    assert serializer.is_valid() is False


def test_pc_edit_rejects_os_change():
    instance = CollectModels(
        name="pc-discovery",
        task_type=CollectPluginTypes.HOST,
        driver_type=CollectDriverTypes.JOB,
        model_id="pc",
        params={"os_type": "windows"},
        credential=WINDOWS_CREDENTIAL,
        timeout=120,
    )
    serializer = _serializer(_payload({"os_type": "macos"}, WINDOWS_CREDENTIAL), instance=instance)
    assert serializer.is_valid() is False
    assert "操作系统" in str(serializer.errors)


def test_pc_macos_password_credential_accepted():
    credential = [{"username": "admin", "password": "secret", "port": 22}]
    serializer = _serializer(_payload({"os_type": "macos"}, credential))
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["params"]["os_type"] == "macos"


def test_pc_macos_private_key_credential_accepted():
    credential = [{"username": "admin", "private_key": "PEM", "passphrase": "pp", "port": 22}]
    serializer = _serializer(_payload({"os_type": "macos"}, credential))
    assert serializer.is_valid(), serializer.errors


def test_pc_macos_rejects_password_and_key_together():
    credential = [{"username": "admin", "password": "secret", "private_key": "PEM", "port": 22}]
    serializer = _serializer(_payload({"os_type": "macos"}, credential))
    assert serializer.is_valid() is False


def test_pc_macos_rejects_credential_without_auth():
    credential = [{"username": "admin", "port": 22}]
    serializer = _serializer(_payload({"os_type": "macos"}, credential))
    assert serializer.is_valid() is False


def test_pc_windows_requires_password():
    credential = [{"username": "alice", "port": 5986}]
    serializer = _serializer(_payload({"os_type": "windows"}, credential))
    assert serializer.is_valid() is False


@pytest.mark.parametrize("timeout", [29, 301])
def test_pc_rejects_timeout_out_of_range(timeout):
    serializer = _serializer(_payload({"os_type": "windows"}, WINDOWS_CREDENTIAL, timeout=timeout))
    assert serializer.is_valid() is False


@pytest.mark.parametrize("timeout", [30, 300])
def test_pc_accepts_timeout_boundary(timeout):
    serializer = _serializer(_payload({"os_type": "windows"}, WINDOWS_CREDENTIAL, timeout=timeout))
    assert serializer.is_valid(), serializer.errors


def test_non_pc_host_task_unaffected():
    payload = _payload({}, [{"username": "root", "password": "secret", "port": 22}], timeout=20, model_id="host")
    serializer = _serializer(payload)
    assert serializer.is_valid(), serializer.errors
