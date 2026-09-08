# -*- coding: utf-8 -*-
import logging
import sys
from pathlib import Path

import pytest

STARGAZER_ROOT = Path(__file__).resolve().parents[1]
if str(STARGAZER_ROOT) not in sys.path:
    sys.path.insert(0, str(STARGAZER_ROOT))

import plugins.inputs.dell_unity.dell_unity_info as unity_module  # noqa: E402
from plugins.inputs.dell_unity.dell_unity_info import DellUnityManager  # noqa: E402

SENTINEL_PASSWORD = "must-not-be-logged"


@pytest.mark.asyncio
async def test_list_all_resources_failure_has_one_traceback(monkeypatch, caplog):
    original = RuntimeError("unity boom")

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def get(self, *_args, **_kwargs):
            raise original

        async def aclose(self):
            return None

    test_logger = logging.getLogger("test.stargazer.dell_unity_collect_failed")
    monkeypatch.setattr(unity_module, "logger", test_logger)
    monkeypatch.setattr(unity_module.httpx, "AsyncClient", FakeAsyncClient)

    plugin = DellUnityManager(
        {
            "host": "10.0.0.20",
            "username": "admin",
            "password": SENTINEL_PASSWORD,
            "collection_task_id": "collect-task-12",
            "verify_tls": False,
        }
    )

    with caplog.at_level(logging.ERROR, logger=test_logger.name):
        result = await plugin.list_all_resources()

    assert result == {"result": {"cmdb_collect_error": "unity boom"}, "success": False}
    error_records = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert len(error_records) == 1
    message = error_records[0].getMessage()
    assert "event=dell_unity_collect_failed" in message
    assert "host=10.0.0.20" in message
    assert "task_id=collect-task-12" in message
    assert "failed_stage=list_all_resources" in message
    assert "error_type=RuntimeError" in message
    assert SENTINEL_PASSWORD not in message
    assert error_records[0].exc_info is not None
    assert error_records[0].exc_info[1] is original
    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert SENTINEL_PASSWORD not in joined
