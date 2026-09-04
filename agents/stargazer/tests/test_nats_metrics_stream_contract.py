import logging
from types import SimpleNamespace

import pytest
from core.collection.application import CollectionApplication, _request_requires_metrics_stream
from core.collection.enums import SubmissionStatus
from core.collection.runtime import CollectionRequest
from core.infra import nats_utils
from core.infra.jetstream_publish_window import JetStreamPublishWindowSettings, JetStreamWindowPublishError
from core.infra.nats_utils import DEFAULT_METRICS_STREAM_NAME, configured_metrics_stream_name, nats_error_log_fields


def test_default_metrics_stream_name_is_metrics(monkeypatch):
    monkeypatch.delenv("NATS_JS_STREAM_NAME", raising=False)

    assert DEFAULT_METRICS_STREAM_NAME == "metrics"
    assert configured_metrics_stream_name() == "metrics"
    assert JetStreamPublishWindowSettings().expected_stream == "metrics"


def test_configured_metrics_stream_name_strips_blank_to_default(monkeypatch):
    monkeypatch.setenv("NATS_JS_STREAM_NAME", "  ")

    assert configured_metrics_stream_name() == "metrics"


def test_nats_error_log_fields_extract_codes_without_payload():
    secret = "SENTINEL_NATS_PAYLOAD"

    class BadRequestError(Exception):
        def __init__(self, description):
            super().__init__(f"payload={secret}")
            self.code = 400
            self.err_code = 10051
            self.description = description

    error = BadRequestError("expected stream does not match subject")

    error_type, nats_code, nats_err_code, description = nats_error_log_fields(error)

    assert error_type == "BadRequestError"
    assert nats_code == 400
    assert nats_err_code == 10051
    assert "expected stream" in description
    assert secret not in description


@pytest.mark.asyncio
async def test_metrics_async_bad_request_is_debug_not_error(monkeypatch, caplog):
    error = type("BadRequestError", (Exception,), {})("expected stream mismatch")
    error.code = 400
    error.err_code = 10051
    error.description = "expected stream does not match"
    test_logger = logging.getLogger("test.stargazer.nats_metrics_async_error")
    monkeypatch.setattr(nats_utils, "logger", test_logger)

    with caplog.at_level(logging.DEBUG, logger=test_logger.name):
        await nats_utils._on_error("metrics", error)

    assert not any(record.levelno >= logging.ERROR for record in caplog.records)
    debug_records = [record for record in caplog.records if record.levelno == logging.DEBUG]
    assert len(debug_records) == 1
    assert debug_records[0].msg == ("event=nats_metrics_async_error error_type=%s nats_code=%s nats_err_code=%s description=%s")
    assert debug_records[0].args == ("BadRequestError", 400, 10051, "expected stream does not match")


@pytest.mark.asyncio
async def test_metrics_publish_logs_one_rejected_summary(monkeypatch, caplog):
    secret = "SENTINEL_NATS_PAYLOAD"
    cause = type("BadRequestError", (Exception,), {})(secret)
    cause.code = 400
    cause.err_code = 10051
    cause.description = "expected stream does not match"

    async def boom(*_args, **_kwargs):
        raise JetStreamWindowPublishError(
            attempted_indices=(0, 1),
            confirmed_indices=(),
            error=cause,
        )

    class FakeWindow:
        async def publish(self, *_args, **_kwargs):
            await boom()

    monkeypatch.setattr(nats_utils, "_get_metrics_js_window", lambda: FakeWindow())
    monkeypatch.delenv("NATS_JS_STREAM_NAME", raising=False)
    test_logger = logging.getLogger("test.stargazer.nats_metrics_publish_rejected")
    monkeypatch.setattr(nats_utils, "logger", test_logger)

    with caplog.at_level(logging.ERROR, logger=test_logger.name):
        with pytest.raises(nats_utils.NatsLinesPublishError):
            await nats_utils._nats_publish_lines_jetstream(
                "metrics.vmware",
                ["line-1", "line-2"],
                before_publish=None,
                message_ids=None,
                deadlines=None,
            )

    records = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert len(records) == 1
    record = records[0]
    assert record.msg == (
        "event=nats_metrics_publish_rejected subject=%s stream=%s rejected_count=%s "
        "attempted_count=%s confirmed_count=%s error_type=%s nats_code=%s nats_err_code=%s "
        "description=%s failed_stage=metrics_publish"
    )
    assert record.args == (
        "metrics.vmware",
        "metrics",
        2,
        2,
        0,
        "BadRequestError",
        400,
        10051,
        "expected stream does not match",
    )
    assert secret not in record.getMessage()
    assert record.exc_info is None


def test_config_file_requests_do_not_require_metrics_stream():
    config_request = CollectionRequest(
        task_id="cfg-1",
        plugin_ref="config_file.config",
        targets=("10.0.0.1",),
        params={"model_id": "config_file", "callback_subject": "receive_config_file_result"},
    )
    vm_request = CollectionRequest(
        task_id="vm-1",
        plugin_ref="vmware.info",
        targets=("10.0.0.2",),
        params={"model_id": "vmware"},
    )

    assert _request_requires_metrics_stream(config_request) is False
    assert _request_requires_metrics_stream(vm_request) is True


@pytest.mark.asyncio
async def test_submit_fails_fast_when_metrics_stream_not_ready(monkeypatch, caplog):
    async def not_ready():
        return False

    called = []

    class Runtime:
        async def submit(self, request):
            called.append(request)
            raise AssertionError("metrics-not-ready tasks must not be admitted")

    monkeypatch.setattr("core.collection.application.metrics_transport_ready", not_ready)
    application = CollectionApplication.__new__(CollectionApplication)
    application.runtime = Runtime()
    application._submission_counts = {}
    request = CollectionRequest(
        task_id="vm-1",
        plugin_ref="vmware.info",
        targets=("10.0.0.2",),
        params={"model_id": "vmware"},
    )
    test_logger = logging.getLogger("test.stargazer.metrics_transport_not_ready")
    monkeypatch.setattr("core.collection.application.logger", test_logger)

    with caplog.at_level(logging.ERROR, logger=test_logger.name):
        submission = await CollectionApplication.submit(application, request)

    assert submission.status == SubmissionStatus.BUSY
    assert submission.reason == "metrics_transport_not_ready"
    assert called == []
    records = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert len(records) == 1
    assert records[0].msg == (
        "event=metrics_transport_not_ready task_id=%s plugin_ref=%s " "failed_stage=run_admission error_type=MetricsTransportNotReady"
    )
    assert records[0].args == ("vm-1", "vmware.info")


@pytest.mark.asyncio
async def test_submit_admits_config_file_when_metrics_stream_not_ready(monkeypatch):
    async def not_ready():
        return False

    admitted = []

    class Runtime:
        async def submit(self, request):
            admitted.append(request.task_id)
            return SimpleNamespace(status=SubmissionStatus.ACCEPTED, task_id=request.task_id)

    monkeypatch.setattr("core.collection.application.metrics_transport_ready", not_ready)
    application = CollectionApplication.__new__(CollectionApplication)
    application.runtime = Runtime()
    application._submission_counts = {}
    request = CollectionRequest(
        task_id="cfg-1",
        plugin_ref="config_file.config",
        targets=("10.0.0.1",),
        params={"model_id": "config_file", "callback_subject": "receive_config_file_result"},
    )

    submission = await CollectionApplication.submit(application, request)

    assert admitted == ["cfg-1"]
    assert submission.status == SubmissionStatus.ACCEPTED
