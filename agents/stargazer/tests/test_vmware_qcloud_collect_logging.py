import logging
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

STARGAZER_ROOT = Path(__file__).resolve().parents[1]
if str(STARGAZER_ROOT) not in sys.path:
    sys.path.insert(0, str(STARGAZER_ROOT))

SENTINEL_PASSWORD = "SENTINEL_COLLECT_PASSWORD_MUST_NOT_LOG"


def _info_messages(caplog):
    return [record.getMessage() for record in caplog.records if record.levelno == logging.INFO]


def _install_pyvmomi_stubs(monkeypatch):
    pyvim = types.ModuleType("pyVim")
    connect = types.ModuleType("pyVim.connect")
    connect.Disconnect = MagicMock()
    connect.SmartConnect = MagicMock()
    pyvim.connect = connect
    pyvmomi = types.ModuleType("pyVmomi")
    pyvmomi.vim = MagicMock()
    monkeypatch.setitem(sys.modules, "pyVim", pyvim)
    monkeypatch.setitem(sys.modules, "pyVim.connect", connect)
    monkeypatch.setitem(sys.modules, "pyVmomi", pyvmomi)


def _load_vmware(monkeypatch):
    _install_pyvmomi_stubs(monkeypatch)
    sys.modules.pop("plugins.inputs.vmware_vc.vmware_info", None)
    sys.modules.pop("tasks.collectors.vmware_collector", None)
    from plugins.inputs.vmware_vc.vmware_info import VmwareManage
    from tasks.collectors import vmware_collector as vmware_module
    from tasks.collectors.vmware_collector import VmwareCollector

    return VmwareManage, vmware_module, VmwareCollector


def test_vmware_collect_sync_summary_and_object_failure(monkeypatch, caplog):
    VmwareManage, vmware_module, VmwareCollector = _load_vmware(monkeypatch)

    original = RuntimeError("vm boom")
    driver = MagicMock()
    driver.get_weops_monitor_data.side_effect = original
    monkeypatch.setattr(vmware_module, "logger", logging.getLogger("test.stargazer.vmware_collect"))

    collector = VmwareCollector(
        {
            "username": "admin",
            "password": SENTINEL_PASSWORD,
            "host": "vcenter.example",
            "collection_task_id": "collect-task-8",
        }
    )

    with (
        patch("common.cmp.driver.CMPDriver", return_value=driver),
        patch.object(VmwareManage, "connect_vc"),
        patch.object(
            VmwareManage,
            "service",
            return_value={
                "vmware_vc": [{"resource_id": "vc-1"}],
                "vmware_vm": [{"resource_id": "vm-1", "ip_addr": "10.0.0.8"}],
            },
        ),
        patch("utils.convert.convert_to_prometheus", return_value=["vmware_metric 1"]),
        caplog.at_level(logging.DEBUG, logger="test.stargazer.vmware_collect"),
    ):
        result = collector._collect_sync()

    assert result.endswith("\n")
    assert "vmware_metric 1" in result
    info_messages = _info_messages(caplog)
    assert len(info_messages) == 1
    assert "event=vmware_collect_summary" in info_messages[0]
    assert "host=vcenter.example" in info_messages[0]
    assert "task_id=collect-task-8" in info_messages[0]
    assert "Processing" not in "\n".join(info_messages)
    assert "=====" not in "\n".join(record.getMessage() for record in caplog.records)

    error_records = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert len(error_records) == 1
    message = error_records[0].getMessage()
    assert "event=vmware_collect_failed" in message
    assert "object_type=vmware_vm" in message
    assert "failed_stage=get_weops_monitor_data" in message
    assert "error_type=RuntimeError" in message
    assert SENTINEL_PASSWORD not in message
    assert error_records[0].exc_info is not None
    assert error_records[0].exc_info[1] is original
    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert SENTINEL_PASSWORD not in joined


def test_vmware_connect_failure_returns_empty(monkeypatch, caplog):
    VmwareManage, vmware_module, VmwareCollector = _load_vmware(monkeypatch)

    original = RuntimeError("connect boom")
    monkeypatch.setattr(vmware_module, "logger", logging.getLogger("test.stargazer.vmware_connect"))

    collector = VmwareCollector(
        {
            "username": "admin",
            "password": SENTINEL_PASSWORD,
            "host": "vcenter.example",
            "collection_task_id": "collect-task-8",
        }
    )
    with (
        patch("common.cmp.driver.CMPDriver", return_value=MagicMock()),
        patch.object(VmwareManage, "connect_vc", side_effect=original),
        caplog.at_level(logging.ERROR, logger="test.stargazer.vmware_connect"),
    ):
        assert collector._collect_sync() == ""

    error_records = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert len(error_records) == 1
    assert "failed_stage=connect_vc" in error_records[0].getMessage()
    assert error_records[0].exc_info[1] is original
    assert SENTINEL_PASSWORD not in error_records[0].getMessage()


def test_qcloud_collect_sync_summary_and_object_failure(monkeypatch, caplog):
    from tasks.collectors import qcloud_collector as qcloud_module
    from tasks.collectors.qcloud_collector import QCloudCollector

    original = RuntimeError("cvm boom")
    driver = MagicMock()
    driver.list_all_resources.return_value = {
        "data": {
            "qcloud_cvm": [{"resource_id": "cvm-1", "inner_ip": "10.0.0.3"}],
        }
    }
    driver.get_weops_monitor_data.side_effect = original
    monkeypatch.setattr(qcloud_module, "logger", logging.getLogger("test.stargazer.qcloud_collect"))

    collector = QCloudCollector(
        {
            "username": "ak",
            "password": SENTINEL_PASSWORD,
            "host": "qcloud.example",
            "region": "ap-guangzhou",
            "collection_task_id": "collect-task-7",
        }
    )
    with (
        patch("common.cmp.driver.CMPDriver", return_value=driver),
        patch("utils.convert.convert_to_prometheus", return_value=[]),
        caplog.at_level(logging.INFO, logger="test.stargazer.qcloud_collect"),
    ):
        result = collector._collect_sync()

    assert "ConnectStatus" in result
    info_messages = _info_messages(caplog)
    assert len(info_messages) == 1
    assert "event=qcloud_collect_summary" in info_messages[0]
    assert "task_id=collect-task-7" in info_messages[0]
    assert "Processing" not in "\n".join(info_messages)

    error_records = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert len(error_records) == 1
    message = error_records[0].getMessage()
    assert "object_type=qcloud_cvm" in message
    assert "failed_stage=get_weops_monitor_data" in message
    assert error_records[0].exc_info[1] is original
    assert SENTINEL_PASSWORD not in message


def test_oceanstor_execute_failure_reraises(monkeypatch, caplog):
    from tasks.collectors import oceanstor_collector as oceanstor_module
    from tasks.collectors.oceanstor_collector import OceanStorCollector

    original = RuntimeError("ocean boom")
    monkeypatch.setattr(oceanstor_module, "logger", logging.getLogger("test.stargazer.oceanstor_collect"))
    monitor = MagicMock()
    monitor.execute.side_effect = original

    collector = OceanStorCollector(
        {
            "username": "admin",
            "password": SENTINEL_PASSWORD,
            "host": "ocean.example",
            "collection_task_id": "collect-task-6",
        }
    )
    with (
        patch("common.monitor_plugins.oceanstor.api.OceanStorApiMonitor", return_value=monitor),
        caplog.at_level(logging.ERROR, logger="test.stargazer.oceanstor_collect"),
        pytest.raises(RuntimeError, match="ocean boom"),
    ):
        collector._collect_sync()

    error_records = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert len(error_records) == 1
    assert "failed_stage=execute" in error_records[0].getMessage()
    assert error_records[0].exc_info[1] is original
    assert SENTINEL_PASSWORD not in error_records[0].getMessage()
