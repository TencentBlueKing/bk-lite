# -*- coding: utf-8 -*-
"""PC 发现 stargazer 侧端到端合同测试。

链路（离线可重复）：
  executor stdout（与 server e2e 共用同一份 fixture）
    → PCInventoryCollector（真实代码，executor 边界 mock）
    → CollectionService._process_result + convert_to_prometheus_format（真实代码）
    → 稳定 Prometheus labels ↔ server 侧 VM rows fixture 逐键一致

锁定：
- windows/macos 资产 label 集合与 server e2e fixture 完全相同（跨仓合同）；
- 完整空快照只落 pc_info + pc_software_info 空标记行；
- partial 快照状态与计数标签原样透出；
- 错误路径只暴露 PC_ERROR_CODES 稳定错误码；
- 秘密（口令/PEM 私钥/密码短语）不出现在 Prometheus 文本与错误标签。
"""
import json
import re
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# server 侧 e2e fixture 是跨仓合同的唯一事实源
SERVER_FIXTURE_DIR = ROOT.parent.parent / "server" / "apps" / "cmdb" / "tests" / "e2e" / "fixtures" / "pc"
LOCAL_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "pc"

SECRET_LITERALS = ("S3cret!Passw0rd#PC", "FAKE-PC-KEY-DATA", "pc-key-passphrase-001")

EXPECTED_ERROR_CODES = frozenset(
    {
        "TARGET_UNREACHABLE",
        "WINRM_AUTH_FAILED",
        "WINRM_TLS_FAILED",
        "SSH_AUTH_FAILED",
        "SSH_KEY_INVALID",
        "SCRIPT_TIMEOUT",
        "PC_IDENTITY_INVALID",
        "SCRIPT_OUTPUT_INVALID",
        "SOFTWARE_PARTIAL",
        "SNAPSHOT_COUNT_MISMATCH",
        "CMDB_WRITE_PARTIAL",
    }
)

# server 连接测试视图认识的错误码必须是全集的子集（前端文案键与之一致）
CONNECTION_TEST_CODES = frozenset(
    {
        "TARGET_UNREACHABLE",
        "WINRM_AUTH_FAILED",
        "WINRM_TLS_FAILED",
        "SSH_AUTH_FAILED",
        "SSH_KEY_INVALID",
        "SCRIPT_TIMEOUT",
        "PC_IDENTITY_INVALID",
        "SCRIPT_OUTPUT_INVALID",
    }
)

_LABEL_RE = re.compile(r'(\w+)="((?:[^"\\]|\\.)*)"')


def _load_server_fixture(name):
    return json.loads((SERVER_FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _parse_prometheus(text):
    """把 convert_to_prometheus_format 输出解析为 {metric_name: [labels, ...]}。"""
    metrics = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        name, rest = line.split("{", 1)
        label_text = rest.rsplit("}", 1)[0]
        labels = {key: value.replace("\\\\", "\\").replace('\\"', '"').replace("\\n", "\n") for key, value in _LABEL_RE.findall(label_text)}
        metrics.setdefault(name, []).append(labels)
    return metrics


def _windows_params(**overrides):
    params = {
        "os_type": "windows",
        "host": "192.168.1.56",
        "node_id": "node-1",
        "username": "ACME\\alice",
        "password": "S3cret!Passw0rd#PC",
        "port": 5986,
        "winrm_scheme": "https",
        "winrm_transport": "ntlm",
        "winrm_cert_validation": False,
        "execute_timeout": 120,
        "script_path": "enterprise/plugins/inputs/pc/pc_windows_discover.ps1",
        "model_id": "pc",
    }
    params.update(overrides)
    return params


def _macos_params(**overrides):
    params = {
        "os_type": "macos",
        "host": "192.168.1.88",
        "node_id": "node-1",
        "username": "admin",
        "private_key": "-----BEGIN OPENSSH PRIVATE KEY-----\nFAKE-PC-KEY-DATA\n-----END OPENSSH PRIVATE KEY-----",
        "passphrase": "pc-key-passphrase-001",
        "port": 22,
        "execute_timeout": 120,
        "script_path": "enterprise/plugins/inputs/pc/pc_macos_discover.sh",
        "model_id": "pc",
    }
    params.update(overrides)
    return params


@pytest.fixture()
def pc_inventory():
    from enterprise.plugins.inputs.pc import pc_inventory as module

    return module


async def _collect(pc_inventory, params, payload, monkeypatch):
    """用固定 executor stdout 跑真实采集器。"""
    if params["os_type"] == "windows":
        mock_ansible = AsyncMock(return_value={"success": True, "result": [{"host": params["host"], "stdout": json.dumps(payload)}]})
        monkeypatch.setattr(pc_inventory, "ansible_adhoc", mock_ansible)
    else:

        class _FakeSSH:
            def __init__(self, _params):
                pass

            async def list_all_resources(self, need_raw=False):
                return {"success": True, "result": json.dumps(payload)}

        monkeypatch.setattr(pc_inventory, "SSHPlugin", _FakeSSH)
    return await pc_inventory.PCInventoryCollector(params).list_all_resources()


def _to_prometheus(result, model_id, host):
    """跑真实 _process_result + convert_to_prometheus_format。"""
    from plugins.base_utils import convert_to_prometheus_format
    from service.collection_service import CollectionService

    service = CollectionService({"model_id": model_id, "host": host})
    processed = service._process_result(result)
    return convert_to_prometheus_format(processed)


# ------------------------------------------------------------ 跨仓 label 合同


@pytest.mark.asyncio
@pytest.mark.parametrize("os_type", ["windows", "macos"])
async def test_prometheus_labels_match_server_vm_fixture(pc_inventory, monkeypatch, os_type):
    payload = _load_server_fixture(f"{os_type}_executor_stdout.json")
    vm_doc = _load_server_fixture(f"{os_type}_vm_rows.json")
    host = vm_doc["data"]["result"][0]["metric"]["host"]
    params = _windows_params() if os_type == "windows" else _macos_params()

    result = await _collect(pc_inventory, params, payload, monkeypatch)
    assert result["success"] is True

    text = _to_prometheus(result, "pc", host)
    metrics = _parse_prometheus(text)

    # 与 server VM fixture 的稳定资产标签一致；旧 fixture 中快照标签不再进入新指标。
    expected_rows = {}
    for row in vm_doc["data"]["result"]:
        metric = dict(row["metric"])
        name = metric.pop("__name__")
        for key in (
            "collection_target",
            "snapshot_id",
            "software_snapshot_status",
            "software_expected_count",
            "software_error_count",
        ):
            metric.pop(key, None)
        expected_rows.setdefault(name, []).append(metric)
    assert metrics == expected_rows

    # server 解析器只从指标读取稳定身份；快照控制字段改走 round metadata。
    pc_labels = metrics["pc_info"][0]
    for key in ("inst_name", "bk_obj_id"):
        assert key in pc_labels
    for key in ("snapshot_id", "software_snapshot_status", "software_expected_count", "software_error_count"):
        assert key not in pc_labels
    sw_labels = metrics["pc_software_info"][0]
    for key in ("inst_name", "pc_inst_name", "software_key", "bk_obj_id"):
        assert key in sw_labels
    assert "snapshot_id" not in sw_labels

    # 秘密不出现在 Prometheus 文本
    for secret in SECRET_LITERALS:
        assert secret not in text
    for metric_labels in metrics.values():
        for labels in metric_labels:
            for key in labels:
                assert key.lower() not in ("password", "private_key", "passphrase")


# ------------------------------------------------------------ 空快照与 partial


@pytest.mark.asyncio
async def test_complete_empty_snapshot_marks_empty_software_stream(pc_inventory, monkeypatch):
    payload = json.loads((LOCAL_FIXTURE_DIR / "windows_empty.json").read_text(encoding="utf-8"))

    result = await _collect(pc_inventory, _windows_params(host="192.168.1.57"), payload, monkeypatch)

    assert result["success"] is True
    assert result["snapshot_status"] == "complete"
    assert result["snapshot_metadata"]["software_expected_count"] == 0
    assert result["result"]["pc_software"] == []

    metrics = _parse_prometheus(_to_prometheus(result, "pc", "192.168.1.57"))
    assert len(metrics["pc_info"]) == 1
    # 空软件流只落空标记行，不带任何软件身份标签
    marker = metrics["pc_software_info"][0]
    assert "inst_name" not in marker
    assert "pc_inst_name" not in marker
    assert marker["collect_status"] == "success"


@pytest.mark.asyncio
async def test_partial_snapshot_metadata_does_not_enter_labels(pc_inventory, monkeypatch):
    payload = json.loads((LOCAL_FIXTURE_DIR / "macos_partial.json").read_text(encoding="utf-8"))
    params = _macos_params(host="192.168.1.99")

    result = await _collect(pc_inventory, params, payload, monkeypatch)

    assert result["success"] is True
    assert result["snapshot_status"] == "partial"
    assert result["snapshot_metadata"] == {
        "software_expected_count": 3,
        "software_error_count": 2,
    }

    metrics = _parse_prometheus(_to_prometheus(result, "pc", "192.168.1.99"))
    assert "software_snapshot_status" not in metrics["pc_info"][0]
    assert "snapshot_id" not in metrics["pc_software_info"][0]


# ------------------------------------------------------------ 错误码与秘密保护


def test_error_code_set_locked(pc_inventory):
    assert pc_inventory.PC_ERROR_CODES == EXPECTED_ERROR_CODES
    assert CONNECTION_TEST_CODES <= pc_inventory.PC_ERROR_CODES


@pytest.mark.asyncio
async def test_executor_failure_exposes_only_stable_code_and_no_secret(pc_inventory, monkeypatch):
    mock_ansible = AsyncMock(
        return_value={
            "success": False,
            "result": [{"host": "192.168.1.56", "unreachable": True, "msg": "timed out connecting with S3cret!Passw0rd#PC"}],
        }
    )
    monkeypatch.setattr(pc_inventory, "ansible_adhoc", mock_ansible)

    result = await pc_inventory.PCInventoryCollector(_windows_params()).list_all_resources()

    assert result["success"] is False
    error_text = result["result"]["cmdb_collect_error"]
    code = error_text.split(":")[0]
    assert code in pc_inventory.PC_ERROR_CODES

    text = _to_prometheus(result, "pc", "192.168.1.56")
    metrics = _parse_prometheus(text)
    error_labels = metrics["pc_info"][0]
    assert error_labels["collect_status"] == "failed"
    for secret in SECRET_LITERALS:
        assert secret not in text
