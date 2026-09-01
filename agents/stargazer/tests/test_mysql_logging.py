import logging

import plugins.inputs.mysql.mysql_info as mysql_info_module
import pytest
from plugins.inputs.mysql.mysql_info import MysqlInfo

SENTINEL_PASSWORD = "SENTINEL_MYSQL_PASSWORD_MUST_NOT_LOG"


@pytest.mark.asyncio
async def test_mysql_list_all_resources_failure_has_traceback(monkeypatch, caplog):
    original = RuntimeError("mysql boom")

    async def boom():
        raise original

    test_logger = logging.getLogger("test.stargazer.mysql_collect_failed")
    monkeypatch.setattr(mysql_info_module, "logger", test_logger)

    plugin = MysqlInfo(
        {
            "host": "10.0.0.3",
            "user": "root",
            "password": SENTINEL_PASSWORD,
            "collection_task_id": "collect-task-9",
        }
    )
    monkeypatch.setattr(plugin, "_connect", boom)

    with caplog.at_level(logging.ERROR, logger=test_logger.name):
        result = await plugin.list_all_resources()

    assert result == {"result": {"cmdb_collect_error": "mysql boom"}, "success": False}
    error_records = [
        record for record in caplog.records if record.levelno == logging.ERROR
    ]
    assert len(error_records) == 1
    message = error_records[0].getMessage()
    assert "event=mysql_collect_failed" in message
    assert "host=10.0.0.3" in message
    assert "task_id=collect-task-9" in message
    assert "failed_stage=list_all_resources" in message
    assert "error_type=RuntimeError" in message
    assert SENTINEL_PASSWORD not in message
    assert error_records[0].exc_info is not None
    assert error_records[0].exc_info[1] is original
    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert SENTINEL_PASSWORD not in joined
    if error_records[0].exc_text:
        assert SENTINEL_PASSWORD not in error_records[0].exc_text
