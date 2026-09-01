import json
import logging

import plugins.inputs.host.host_info as host_info_module
import plugins.script_executor as script_executor_module
import pytest
from plugins.inputs.host.host_info import HostInfo
from plugins.script_executor import SSHPlugin

SENTINEL_INVENTORY = "SENTINEL_HOST_INVENTORY_MUST_NOT_LOG"
SENTINEL_PROC = "SENTINEL_PROC_MUST_NOT_LOG"


def _plugin_params(tmp_path, **extra):
    script_path = tmp_path / "collect.sh"
    script_path.write_text("echo ok", encoding="utf-8")
    params = {
        "node_id": "node-1",
        "host": "10.0.0.1",
        "script_path": str(script_path),
        "model_id": "host",
        "collection_task_id": "collect-task-9",
    }
    params.update(extra)
    return params


@pytest.mark.asyncio
async def test_host_collect_success_does_not_log_inventory(
    tmp_path, monkeypatch, caplog
):
    payload = json.dumps(
        [
            {
                "host": SENTINEL_INVENTORY,
                "ip_addr": "10.0.0.1",
                "proc": [{"name": SENTINEL_PROC, "pid": 42}],
            }
        ]
    )

    async def fake_nats_request(*_args, **_kwargs):
        return {"success": True, "result": payload}

    test_logger = logging.getLogger("test.stargazer.host_ssh_collect")
    monkeypatch.setattr(script_executor_module, "nats_request", fake_nats_request)
    monkeypatch.setattr(script_executor_module, "logger", test_logger)
    monkeypatch.setattr(host_info_module, "logger", test_logger)

    plugin = HostInfo(_plugin_params(tmp_path))
    with caplog.at_level(logging.DEBUG, logger=test_logger.name):
        result = await plugin.list_all_resources()

    assert result["success"] is True
    assert result["result"]["host"][0]["host"] == SENTINEL_INVENTORY
    assert result["result"]["host_proc_usage"][0]["name"] == SENTINEL_PROC
    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert SENTINEL_INVENTORY not in joined
    assert SENTINEL_PROC not in joined
    info_messages = [
        record.getMessage()
        for record in caplog.records
        if record.levelno == logging.INFO
    ]
    assert len(info_messages) == 1
    assert "event=host_collect_completed" in info_messages[0]
    assert "host=10.0.0.1" in info_messages[0]
    assert "model_id=host" in info_messages[0]
    assert "task_id=collect-task-9" in info_messages[0]
    assert "host_count=1" in info_messages[0]
    assert "proc_count=1" in info_messages[0]


@pytest.mark.asyncio
async def test_ssh_script_failure_has_one_traceback_error(
    tmp_path, monkeypatch, caplog
):
    original = RuntimeError("ssh failed")

    async def fake_nats_request(*_args, **_kwargs):
        raise original

    test_logger = logging.getLogger("test.stargazer.ssh_script_failed")
    monkeypatch.setattr(script_executor_module, "nats_request", fake_nats_request)
    monkeypatch.setattr(script_executor_module, "logger", test_logger)

    plugin = SSHPlugin(_plugin_params(tmp_path, password="must-not-be-logged"))
    with caplog.at_level(logging.INFO, logger=test_logger.name):
        result = await plugin.list_all_resources()

    assert result["success"] is False
    assert result["result"]["cmdb_collect_error"] == "ssh failed"
    error_records = [
        record for record in caplog.records if record.levelno == logging.ERROR
    ]
    assert len(error_records) == 1
    message = error_records[0].getMessage()
    assert "event=ssh_script_failed" in message
    assert "task_id=collect-task-9" in message
    assert "host=10.0.0.1" in message
    assert "model_id=host" in message
    assert "failed_stage=ssh_script_execute" in message
    assert "error_type=RuntimeError" in message
    assert "must-not-be-logged" not in message
    assert error_records[0].exc_info is not None
    assert error_records[0].exc_info[1] is original
    assert not any(record.levelno == logging.INFO for record in caplog.records)


@pytest.mark.asyncio
async def test_host_parse_failure_has_traceback_and_unchanged_return(
    tmp_path, monkeypatch, caplog
):
    async def fake_nats_request(*_args, **_kwargs):
        return {"success": True, "result": "{}"}

    def boom(_collect_output):
        raise ValueError("parse boom")

    test_logger = logging.getLogger("test.stargazer.host_parse_failed")
    monkeypatch.setattr(script_executor_module, "nats_request", fake_nats_request)
    monkeypatch.setattr(script_executor_module, "logger", test_logger)
    monkeypatch.setattr(host_info_module, "logger", test_logger)

    plugin = HostInfo(_plugin_params(tmp_path))
    monkeypatch.setattr(plugin, "_parse_collect_output", boom)
    with caplog.at_level(logging.ERROR, logger=test_logger.name):
        result = await plugin.list_all_resources()

    assert result == {"result": {"cmdb_collect_error": "parse boom"}, "success": False}
    error_records = [
        record for record in caplog.records if record.levelno == logging.ERROR
    ]
    assert len(error_records) == 1
    assert "event=host_collect_failed" in error_records[0].getMessage()
    assert "failed_stage=host_parse" in error_records[0].getMessage()
    assert "task_id=collect-task-9" in error_records[0].getMessage()
    assert error_records[0].exc_info is not None
