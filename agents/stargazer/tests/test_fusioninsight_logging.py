import logging

import plugins.inputs.fusioninsight.fusioninsight_info as fusioninsight_module
import pytest
from plugins.inputs.fusioninsight.fusioninsight_info import (
    FusionInsightManager,
    handle_request,
)

SENTINEL_HTTP_BODY = "SENTINEL_HTTP_BODY"
SENTINEL_PASSWORD = "must-not-be-logged"


class _FakeResp:
    def __init__(self, status_code, text="", payload=None):
        self.status_code = status_code
        self.text = text
        self.content = (
            b"{}" if payload is not None else (text.encode("utf-8") if text else b"")
        )
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_http_500_does_not_log_body(monkeypatch, caplog):
    class FakeClient:
        async def request(self, method, url, **kwargs):
            return _FakeResp(500, text=SENTINEL_HTTP_BODY)

    test_logger = logging.getLogger("test.stargazer.fusioninsight_http_500")
    monkeypatch.setattr(fusioninsight_module, "logger", test_logger)

    with caplog.at_level(logging.DEBUG, logger=test_logger.name):
        result = await handle_request(
            "GET", "https://fi.example.com/web/api/v2/hosts", FakeClient()
        )

    assert result["result"] is False
    assert SENTINEL_HTTP_BODY in result["message"]
    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert SENTINEL_HTTP_BODY not in joined
    error_records = [
        record for record in caplog.records if record.levelno == logging.ERROR
    ]
    assert len(error_records) == 1
    message = error_records[0].getMessage()
    assert "event=fusioninsight_http_failed" in message
    assert "url=https://fi.example.com/web/api/v2/hosts" in message
    assert "method=GET" in message
    assert "status_code=500" in message


@pytest.mark.asyncio
async def test_success_http_is_not_info(monkeypatch, caplog):
    class FakeClient:
        async def request(self, method, url, **kwargs):
            return _FakeResp(200, text=SENTINEL_HTTP_BODY, payload={"ok": True})

    test_logger = logging.getLogger("test.stargazer.fusioninsight_http_ok")
    monkeypatch.setattr(fusioninsight_module, "logger", test_logger)

    with caplog.at_level(logging.DEBUG, logger=test_logger.name):
        result = await handle_request(
            "GET", "https://fi.example.com/web/api/v2/hosts", FakeClient()
        )

    assert result["result"] is True
    assert result["data"] == {"ok": True}
    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert SENTINEL_HTTP_BODY not in joined
    assert not any(record.levelno == logging.INFO for record in caplog.records)
    debug_messages = [
        record.getMessage()
        for record in caplog.records
        if record.levelno == logging.DEBUG
    ]
    assert any("event=fusioninsight_http_ok" in message for message in debug_messages)


@pytest.mark.asyncio
async def test_list_all_resources_failure_has_one_traceback(monkeypatch, caplog):
    original = RuntimeError("fi boom")

    async def boom():
        raise original

    test_logger = logging.getLogger("test.stargazer.fusioninsight_collect_failed")
    monkeypatch.setattr(fusioninsight_module, "logger", test_logger)

    plugin = FusionInsightManager(
        {
            "host": "10.0.0.2",
            "username": "admin",
            "password": SENTINEL_PASSWORD,
            "collection_task_id": "collect-task-9",
            "verify_tls": False,
        }
    )
    monkeypatch.setattr(plugin, "exec_script", boom)

    with caplog.at_level(logging.ERROR, logger=test_logger.name):
        result = await plugin.list_all_resources()

    assert result == {"result": {"cmdb_collect_error": "fi boom"}, "success": False}
    error_records = [
        record for record in caplog.records if record.levelno == logging.ERROR
    ]
    assert len(error_records) == 1
    message = error_records[0].getMessage()
    assert "event=fusioninsight_collect_failed" in message
    assert "host=10.0.0.2" in message
    assert "task_id=collect-task-9" in message
    assert "failed_stage=list_all_resources" in message
    assert "error_type=RuntimeError" in message
    assert SENTINEL_PASSWORD not in message
    assert error_records[0].exc_info is not None
    assert error_records[0].exc_info[1] is original
    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert SENTINEL_PASSWORD not in joined
