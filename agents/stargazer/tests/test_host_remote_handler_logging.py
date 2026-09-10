import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest
from tasks.handlers import host_remote_handler
from tasks.utils import nats_helper


@pytest.mark.asyncio
async def test_retryable_host_remote_publish_failure_is_one_bounded_warning(monkeypatch):
    context = {
        "ctx": {},
        "params": {"model_id": "host", "monitor_type": "host"},
        "raw_callback": {"success": True, "result": []},
    }
    monkeypatch.setattr(
        host_remote_handler.host_remote_callback,
        "load_host_remote_callback_context",
        AsyncMock(return_value=context),
    )
    monkeypatch.setattr(
        host_remote_handler.host_remote_callback,
        "mark_host_remote_processing_started",
        AsyncMock(),
    )
    monkeypatch.setattr(
        host_remote_handler.host_remote_callback,
        "is_retryable_host_remote_publish_error",
        lambda _error: True,
    )
    monkeypatch.setattr(
        host_remote_handler.host_remote_callback,
        "schedule_host_remote_publish_retry",
        AsyncMock(return_value={"retry_scheduled": True, "attempt": 1, "next_retry_at": 2}),
    )
    collector_module = types.ModuleType("tasks.collectors.host_collector")

    class HostCollector:
        def __init__(self, _params):
            pass

        def process_adhoc_result(self, _callback):
            return "host_metric 1"

    collector_module.HostCollector = HostCollector
    monkeypatch.setitem(sys.modules, "tasks.collectors.host_collector", collector_module)
    monkeypatch.setattr(
        nats_helper,
        "publish_metrics_to_nats",
        AsyncMock(side_effect=RuntimeError("SENSITIVE_PUBLISH_BODY")),
    )
    test_logger = MagicMock()
    monkeypatch.setattr(host_remote_handler, "logger", test_logger)

    result = await host_remote_handler.process_host_remote_callback_task({}, {}, "remote-1")

    assert result["status"] == "retry_scheduled"
    test_logger.error.assert_not_called()
    assert test_logger.warning.call_args.args == (
        "event=host_remote_publish_failed task_id=%s failed_stage=%s error_type=%s",
        "remote-1",
        "metrics_publish",
        "RuntimeError",
    )
    assert "SENSITIVE_PUBLISH_BODY" not in str(test_logger.warning.call_args)
