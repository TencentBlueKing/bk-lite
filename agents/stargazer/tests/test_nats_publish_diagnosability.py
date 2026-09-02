import logging

import pytest
from core.infra import nats_utils
from tasks.utils import nats_helper


class _FailingNats:
    def __init__(self, error):
        self.error = error

    async def publish(self, _subject, _payload):
        raise self.error

    async def flush(self):
        raise AssertionError("flush should not run after publish failure")


@pytest.mark.asyncio
async def test_callback_publish_failure_has_one_error_owner_with_traceback(monkeypatch, caplog):
    original_error = ConnectionError("nats unavailable")

    async def get_failing_nats(_channel):
        return _FailingNats(original_error)

    test_logger = logging.getLogger("test.stargazer.callback_publish")
    monkeypatch.setattr(nats_utils, "get_shared_nats", get_failing_nats)
    monkeypatch.setattr(nats_utils, "logger", test_logger)
    monkeypatch.setattr(nats_helper, "logger", test_logger)

    with caplog.at_level(logging.ERROR, logger=test_logger.name):
        with pytest.raises(ConnectionError, match="nats unavailable") as caught:
            await nats_helper.publish_callback_to_nats(
                {"status": "error", "credential": "must-not-be-logged"},
                {"callback_subject": "receive_config_file_result"},
                "run-1",
            )

    assert caught.value is original_error
    error_records = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert len(error_records) == 1
    assert "event=callback_publish_failed" in error_records[0].getMessage()
    assert "task_id=run-1" in error_records[0].getMessage()
    assert "subject=bklite.receive_config_file_result" in error_records[0].getMessage()
    assert "failed_stage=callback_publish" in error_records[0].getMessage()
    assert "error_type=ConnectionError" in error_records[0].getMessage()
    assert "must-not-be-logged" not in error_records[0].getMessage()
    assert error_records[0].exc_info is not None


def test_credential_result_nats_helper_is_removed():
    assert not hasattr(nats_helper, "publish_credential_result_to_nats")
