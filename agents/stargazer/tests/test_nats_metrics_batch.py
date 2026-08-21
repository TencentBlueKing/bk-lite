import asyncio
import time
from collections import deque
from types import SimpleNamespace

import pytest
from core.collection.contracts import StructuredMetricsPayload
from core.collection.metrics import CollectionMetrics
from core.infra import nats_utils
from plugins.base_utils import convert_to_prometheus_format
from tasks.utils import nats_helper


def test_structured_metrics_encoder_matches_legacy_prometheus_round_trip(monkeypatch):
    monkeypatch.setattr("plugins.base_utils.time.time", lambda: 1700000000.123)
    monkeypatch.setattr(nats_helper.time, "time", lambda: 1700000000.123)
    data = {
        "network_system": [
            {
                "host": "10.10.24.1",
                "port": 161,
                "sysname": "switch-a",
                "empty": "",
                "nested": {"ignored": True},
            }
        ]
    }
    params = {
        "host": "10.10.24.1",
        "model_id": "network",
        "collection_result_id": "result-1",
    }

    legacy = nats_helper.convert_prometheus_to_influx(convert_to_prometheus_format(data), params)
    structured = nats_helper.convert_structured_metrics_to_influx(StructuredMetricsPayload(data=data), params)

    assert structured == legacy


@pytest.mark.asyncio
async def test_metrics_batch_isolates_conversion_failure_to_one_result(monkeypatch):
    published = []

    def convert(metrics, params):
        if metrics == "broken":
            raise ValueError("invalid metrics")
        return [f"line-{params['collection_result_id']}"]

    async def publish(subject, lines, task_id):
        published.append((subject, lines, task_id))
        return len(lines)

    monkeypatch.setattr(nats_helper, "_iter_metrics_to_influx", convert)
    monkeypatch.setattr(nats_helper, "_publish_lines_with_retry", publish)
    outcomes = await nats_helper.publish_metrics_batch_to_nats(
        (
            (
                {},
                "valid",
                {"model_id": "network", "collection_result_id": "ok"},
                "run-1",
            ),
            (
                {},
                "broken",
                {"model_id": "network", "collection_result_id": "bad"},
                "run-1",
            ),
        )
    )

    assert outcomes["ok"] is None
    assert isinstance(outcomes["bad"], ValueError)
    assert published == [("metrics.network", ["line-ok"], "run-1")]


@pytest.mark.asyncio
async def test_metrics_batch_isolates_subject_failure_from_other_subjects(monkeypatch):
    def convert(_metrics, params):
        return [f"line-{params['collection_result_id']}"]

    async def publish(subject, lines, task_id):
        if subject == "metrics.network":
            raise TimeoutError("network subject failed")
        return len(lines)

    monkeypatch.setattr(nats_helper, "_iter_metrics_to_influx", convert)
    monkeypatch.setattr(nats_helper, "_publish_lines_with_retry", publish)
    outcomes = await nats_helper.publish_metrics_batch_to_nats(
        (
            (
                {},
                "a",
                {"model_id": "network", "collection_result_id": "network-1"},
                "run-1",
            ),
            (
                {},
                "b",
                {"model_id": "mysql", "collection_result_id": "mysql-1"},
                "run-1",
            ),
        )
    )

    assert isinstance(outcomes["network-1"], nats_helper.MetricsPublishError)
    assert outcomes["network-1"].delivery_detected is False
    assert outcomes["mysql-1"] is None


@pytest.mark.asyncio
async def test_metrics_batch_isolates_transport_failure_to_one_target_with_same_subject(
    monkeypatch,
):
    def convert(_metrics, params):
        return [f"line-{params['collection_result_id']}"]

    async def publish(_subject, lines, _task_id):
        if lines == ["line-bad"]:
            raise TimeoutError("one target failed")
        return len(lines)

    monkeypatch.setattr(nats_helper, "_iter_metrics_to_influx", convert)
    monkeypatch.setattr(nats_helper, "_publish_lines_with_retry", publish)
    # 两个目标位于不同的有界 chunk；第二个 chunk 失败不能回滚第一个已确认 chunk。
    monkeypatch.setattr(nats_helper, "MAX_NATS_LINES_PER_FLUSH", 1)

    outcomes = await nats_helper.publish_metrics_batch_to_nats(
        (
            ({}, "ok", {"model_id": "network", "collection_result_id": "ok"}, "run-1"),
            (
                {},
                "bad",
                {"model_id": "network", "collection_result_id": "bad"},
                "run-1",
            ),
        )
    )

    assert outcomes["ok"] is None
    assert isinstance(outcomes["bad"], nats_helper.MetricsPublishError)
    assert outcomes["bad"].delivery_detected is False


def test_line_chunks_are_bounded_by_count_and_utf8_bytes():
    chunks = list(nats_helper._iter_line_chunks(["a" * 4, "中", "b" * 4, "c"], max_lines=2, max_bytes=7))

    assert chunks == [["a" * 4, "中"], ["b" * 4, "c"]]
    assert all(len(chunk) <= 2 for chunk in chunks)
    assert all(sum(len(line.encode("utf-8")) for line in chunk) <= 7 for chunk in chunks)


@pytest.mark.asyncio
async def test_oversized_metric_line_only_fails_its_target(monkeypatch):
    def convert(_metrics, params):
        if params["collection_result_id"] == "large":
            return ["x" * (nats_helper.MAX_NATS_LINE_BYTES + 1)]
        return ["ok"]

    published = []

    async def publish(subject, lines, task_id):
        published.append((subject, lines, task_id))
        return len(lines)

    monkeypatch.setattr(nats_helper, "_iter_metrics_to_influx", convert)
    monkeypatch.setattr(nats_helper, "_publish_lines_with_retry", publish)
    outcomes = await nats_helper.publish_metrics_batch_to_nats(
        (
            (
                {},
                "large",
                {"model_id": "network", "collection_result_id": "large"},
                "run-1",
            ),
            (
                {},
                "small",
                {"model_id": "network", "collection_result_id": "small"},
                "run-1",
            ),
        )
    )

    assert isinstance(outcomes["large"], ValueError)
    assert outcomes["small"] is None
    assert published == [("metrics.network", ["ok"], "run-1")]


@pytest.mark.asyncio
async def test_nats_helper_performs_only_one_low_level_attempt(monkeypatch):
    attempts = 0

    async def fail_before_delivery(_subject, _lines):
        nonlocal attempts
        attempts += 1
        return 0

    monkeypatch.setattr(nats_helper, "nats_publish_lines", fail_before_delivery)

    with pytest.raises(nats_helper.MetricsPublishError) as error:
        await nats_helper._publish_lines_with_retry("metrics.network", ["line"], "run-1")

    assert attempts == 1
    assert error.value.delivery_detected is False
    assert error.value.attempts == 1


@pytest.mark.asyncio
async def test_successful_metrics_publish_is_visible_at_info_level(monkeypatch):
    info_logs = []

    async def publish_lines(_subject, lines):
        return len(lines)

    def capture_info(message, *args):
        info_logs.append(message % args if args else message)

    monkeypatch.setattr(nats_helper, "nats_publish_lines", publish_lines)
    monkeypatch.setattr(nats_helper.logger, "info", capture_info)

    published = await nats_helper._publish_lines_with_retry("metrics.snmp_facts", ["line-1", "line-2"], "run-snmp-1")

    assert published == 2
    assert len(info_logs) == 1
    assert "event=nats_metrics_publish_succeeded" in info_logs[0]
    assert "task_id=run-snmp-1" in info_logs[0]
    assert "subject=metrics.snmp_facts" in info_logs[0]
    assert "NATS指标推送成功" in info_logs[0]
    assert "成功行数=2/2" in info_logs[0]


@pytest.mark.asyncio
async def test_nats_connection_failure_is_marked_as_not_delivered(monkeypatch):
    async def connection_failed(*_args, **_kwargs):
        raise ConnectionError("connect failed")

    monkeypatch.setattr(nats_utils, "get_shared_nats", connection_failed)

    with pytest.raises(nats_utils.NatsLinesPublishError) as error:
        await nats_utils.nats_publish_lines("metrics.network", ["line"])

    assert error.value.attempted_count_before_failure == 0
    assert error.value.delivery_detected is False


@pytest.mark.asyncio
async def test_metrics_flush_uses_delivery_timeout(monkeypatch):
    flush_timeouts = []

    class FakeNats:
        async def publish(self, _subject, _payload):
            return None

        async def flush(self, timeout=None):
            flush_timeouts.append(timeout)

    async def get_nats(*_args, **_kwargs):
        return FakeNats()

    monkeypatch.setenv("PUBLISH_DELIVERY_TIMEOUT", "17")
    monkeypatch.setattr(nats_utils, "get_shared_nats", get_nats)

    assert await nats_utils.nats_publish_lines("metrics.network", ["line"]) == 1
    assert flush_timeouts == [17.0]


@pytest.mark.asyncio
async def test_metrics_delivery_timeout_also_bounds_connection_wait(monkeypatch):
    async def slow_connect(_channel="control"):
        await asyncio.sleep(1)

    monkeypatch.setenv("PUBLISH_DELIVERY_TIMEOUT", "0.01")
    monkeypatch.setattr(nats_utils, "get_shared_nats", slow_connect)

    with pytest.raises(nats_utils.NatsLinesPublishError) as exc_info:
        await nats_utils.nats_publish_lines("metrics.network", ["line"])

    assert exc_info.value.delivery_detected is False
    assert isinstance(exc_info.value.error, TimeoutError)


@pytest.mark.asyncio
async def test_shared_nats_reuses_connection_while_client_is_reconnecting(monkeypatch):
    class ReconnectingNats:
        is_connected = False
        is_reconnecting = True
        is_closed = False

        async def close(self):
            raise AssertionError("reconnecting connection must not be closed")

    reconnecting = ReconnectingNats()
    monkeypatch.setattr(nats_utils, "_shared_nc", reconnecting)

    assert await nats_utils.get_shared_nats() is reconnecting


@pytest.mark.asyncio
async def test_metrics_and_control_publishes_use_separate_connection_channels(
    monkeypatch,
):
    channels = []

    class FakeNats:
        async def publish(self, _subject, _payload):
            return None

        async def flush(self, timeout=None):
            return None

    async def get_nats(channel="control"):
        channels.append(channel)
        return FakeNats()

    monkeypatch.setattr(nats_utils, "get_shared_nats", get_nats)

    await nats_utils.nats_publish("callback.subject", {"ok": True})
    await nats_utils.nats_publish_lines("metrics.network", ["line"])

    assert channels == ["control", "metrics"]


@pytest.mark.asyncio
async def test_close_shared_nats_closes_both_channels_even_when_drain_fails(
    monkeypatch,
):
    closed = []

    class FakeConnection:
        is_closed = False

        def __init__(self, name, *, fail_drain=False):
            self.name = name
            self.fail_drain = fail_drain

        async def drain(self):
            if self.fail_drain:
                raise ConnectionError("drain failed")

        async def close(self):
            closed.append(self.name)

    monkeypatch.setattr(nats_utils, "_shared_nc", FakeConnection("control", fail_drain=True))
    monkeypatch.setattr(nats_utils, "_metrics_nc", FakeConnection("metrics"))

    await nats_utils.close_shared_nats()

    assert closed == ["control", "metrics"]
    assert nats_utils._shared_nc is None
    assert nats_utils._metrics_nc is None


def test_nats_metrics_connection_stats_expose_connection_and_pending_bytes(monkeypatch):
    connection = SimpleNamespace(
        is_connected=True,
        is_reconnecting=False,
        pending_data_size=1234,
    )
    monkeypatch.setattr(nats_utils, "_metrics_nc", connection)
    monkeypatch.setattr(nats_utils, "_metrics_reconnect_total", 3)
    monkeypatch.setattr(nats_utils, "_metrics_reconnect_duration_seconds", 1.25)
    monkeypatch.setattr(nats_utils, "_metrics_reconnect_durations", deque((0.5, 1.25), maxlen=500))

    assert nats_utils.nats_metrics_connection_stats() == {
        "nats_metrics_connected": 1,
        "nats_metrics_reconnecting": 0,
        "nats_metrics_reconnect_total": 3,
        "nats_metrics_reconnect_duration_seconds": 1.25,
        "nats_metrics_reconnect_duration_seconds_p99": 0.5,
        "nats_metrics_pending_bytes": 1234,
    }


@pytest.mark.asyncio
async def test_large_metrics_encoding_does_not_block_event_loop(monkeypatch):
    ticks = 0

    def slow_convert(_metrics, _params):
        time.sleep(0.05)
        yield "line"

    async def publish(_subject, lines, _task_id):
        return len(lines)

    async def heartbeat():
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.005)

    monkeypatch.setattr(nats_helper, "_iter_metrics_to_influx", slow_convert)
    monkeypatch.setattr(nats_helper, "_publish_lines_with_retry", publish)
    heartbeat_task = asyncio.create_task(heartbeat())
    try:
        outcomes = await nats_helper.publish_metrics_batch_to_nats(
            (
                (
                    {},
                    "metrics",
                    {"model_id": "network", "collection_result_id": "one"},
                    "run-1",
                ),
            )
        )
    finally:
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)

    assert outcomes["one"] is None
    assert ticks >= 5


@pytest.mark.asyncio
async def test_metrics_batch_encodes_and_publishes_in_bounded_chunks(monkeypatch):
    produced = 0
    produced_at_first_publish = None

    def iter_lines(_metrics, _params):
        nonlocal produced
        for index in range(5):
            produced += 1
            yield f"line-{index}"

    async def publish(_subject, lines, _task_id):
        nonlocal produced_at_first_publish
        if produced_at_first_publish is None:
            produced_at_first_publish = produced
        assert len(lines) <= 2
        return len(lines)

    monkeypatch.setattr(nats_helper, "_iter_metrics_to_influx", iter_lines)
    monkeypatch.setattr(nats_helper, "_publish_lines_with_retry", publish)
    monkeypatch.setattr(nats_helper, "MAX_NATS_LINES_PER_FLUSH", 2)

    outcomes = await nats_helper.publish_metrics_batch_to_nats(
        (
            (
                {},
                "metrics",
                {"model_id": "network", "collection_result_id": "one"},
                "run-1",
            ),
        )
    )

    assert outcomes["one"] is None
    assert produced_at_first_publish < produced


@pytest.mark.asyncio
async def test_metrics_batch_records_actual_line_and_byte_counts(monkeypatch):
    metrics = CollectionMetrics()

    def iter_lines(_metrics, _params):
        yield "a"
        yield "中"

    async def publish(_subject, lines, _task_id):
        return len(lines)

    monkeypatch.setattr(nats_helper, "_iter_metrics_to_influx", iter_lines)
    monkeypatch.setattr(nats_helper, "_publish_lines_with_retry", publish)

    outcomes = await nats_helper.publish_metrics_batch_to_nats(
        (
            (
                {},
                "metrics",
                {"model_id": "network", "collection_result_id": "one"},
                "run-1",
            ),
        ),
        metrics=metrics,
    )

    snapshot = metrics.snapshot()
    assert outcomes["one"] is None
    assert snapshot["publish_lines_total"] == 2
    assert snapshot["publish_bytes_total"] == 4


@pytest.mark.asyncio
async def test_same_subject_success_and_failure_results_share_one_flush(monkeypatch):
    published = []

    def iter_lines(metrics, params):
        if metrics == "success":
            yield f"success-a-{params['collection_result_id']}"
            yield f"success-b-{params['collection_result_id']}"
            return
        yield f"failed-{params['collection_result_id']}"

    async def publish(subject, lines, task_id):
        published.append((subject, tuple(lines), task_id))
        return len(lines)

    monkeypatch.setattr(nats_helper, "_iter_metrics_to_influx", iter_lines)
    monkeypatch.setattr(nats_helper, "_publish_lines_with_retry", publish)

    outcomes = await nats_helper.publish_metrics_batch_to_nats(
        (
            (
                {},
                "success",
                {"model_id": "network", "collection_result_id": "ok"},
                "run-1",
            ),
            (
                {},
                "failed",
                {"model_id": "network", "collection_result_id": "bad"},
                "run-1",
            ),
        )
    )

    assert outcomes == {"ok": None, "bad": None}
    assert published == [
        (
            "metrics.network",
            ("success-a-ok", "success-b-ok", "failed-bad"),
            "run-1",
        )
    ]


@pytest.mark.asyncio
async def test_partial_chunk_failure_only_marks_attempted_results_as_unknown(
    monkeypatch,
):
    def iter_lines(_metrics, params):
        yield f"line-{params['collection_result_id']}"

    async def publish(subject, lines, task_id):
        raise nats_helper.MetricsPublishError(
            task_id=task_id,
            subject=subject,
            total_lines=len(lines),
            success_count=0,
            delivery_detected=True,
            attempts=1,
            reason="flush_timeout",
            attempted_count=1,
        )

    monkeypatch.setattr(nats_helper, "_iter_metrics_to_influx", iter_lines)
    monkeypatch.setattr(nats_helper, "_publish_lines_with_retry", publish)

    outcomes = await nats_helper.publish_metrics_batch_to_nats(
        (
            (
                {},
                "a",
                {"model_id": "network", "collection_result_id": "first"},
                "run-1",
            ),
            (
                {},
                "b",
                {"model_id": "network", "collection_result_id": "second"},
                "run-1",
            ),
        )
    )

    assert outcomes["first"].delivery_detected is True
    assert outcomes["second"].delivery_detected is False


@pytest.mark.asyncio
async def test_result_total_line_limit_only_rejects_oversized_target(monkeypatch):
    published = []

    def iter_lines(_metrics, params):
        count = 3 if params["collection_result_id"] == "large" else 1
        for index in range(count):
            yield f"line-{params['collection_result_id']}-{index}"

    async def publish(subject, lines, task_id):
        published.extend(lines)
        return len(lines)

    monkeypatch.setattr(nats_helper, "_iter_metrics_to_influx", iter_lines)
    monkeypatch.setattr(nats_helper, "_publish_lines_with_retry", publish)
    monkeypatch.setattr(nats_helper, "MAX_NATS_LINES_PER_RESULT", 2)
    monkeypatch.setattr(nats_helper, "MAX_NATS_LINES_PER_FLUSH", 1)

    outcomes = await nats_helper.publish_metrics_batch_to_nats(
        (
            (
                {},
                "a",
                {"model_id": "network", "collection_result_id": "large"},
                "run-1",
            ),
            (
                {},
                "b",
                {"model_id": "network", "collection_result_id": "small"},
                "run-1",
            ),
        )
    )

    assert isinstance(outcomes["large"], ValueError)
    assert outcomes["small"] is None
    assert "line-small-0" in published
    assert not any(line.startswith("line-large-") for line in published)


@pytest.mark.asyncio
async def test_large_subject_does_not_starve_small_different_subject(monkeypatch):
    published = []

    def iter_lines(_metrics, params):
        count = 3 if params["collection_result_id"] == "large" else 1
        for index in range(count):
            yield f"{params['collection_result_id']}-{index}"

    async def publish(subject, lines, _task_id):
        published.extend((subject, line) for line in lines)
        return len(lines)

    monkeypatch.setattr(nats_helper, "_iter_metrics_to_influx", iter_lines)
    monkeypatch.setattr(nats_helper, "_publish_lines_with_retry", publish)
    monkeypatch.setattr(nats_helper, "MAX_NATS_LINES_PER_FLUSH", 1)

    await nats_helper.publish_metrics_batch_to_nats(
        (
            (
                {},
                "a",
                {"model_id": "network", "collection_result_id": "large"},
                "run-1",
            ),
            ({}, "b", {"model_id": "mysql", "collection_result_id": "small"}, "run-2"),
        )
    )

    assert published[:2] == [
        ("metrics.network", "large-0"),
        ("metrics.mysql", "small-0"),
    ]


@pytest.mark.asyncio
async def test_large_target_does_not_starve_small_target_with_same_subject(monkeypatch):
    published = []

    def iter_lines(_metrics, params):
        count = 5 if params["collection_result_id"] == "large" else 1
        for index in range(count):
            yield f"{params['collection_result_id']}-{index}"

    async def publish(_subject, lines, _task_id):
        published.extend(lines)
        return len(lines)

    monkeypatch.setattr(nats_helper, "_iter_metrics_to_influx", iter_lines)
    monkeypatch.setattr(nats_helper, "_publish_lines_with_retry", publish)
    monkeypatch.setattr(nats_helper, "MAX_NATS_LINES_PER_FLUSH", 1)

    await nats_helper.publish_metrics_batch_to_nats(
        (
            (
                {},
                "a",
                {"model_id": "network", "collection_result_id": "large"},
                "run-1",
            ),
            (
                {},
                "b",
                {"model_id": "network", "collection_result_id": "small"},
                "run-2",
            ),
        )
    )

    assert published[:2] == ["large-0", "small-0"]
