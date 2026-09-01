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


@pytest.fixture(autouse=True)
def _explicit_core_nats_compatibility_for_legacy_transport_tests(monkeypatch):
    monkeypatch.setenv("NATS_METRICS_JETSTREAM_ENABLED", "false")
    monkeypatch.setenv("NATS_METRICS_CORE_FALLBACK_ENABLED", "true")


def _series_key(line: str) -> str:
    return line.partition(" ")[0]


def test_collection_run_identity_does_not_change_business_metric_series():
    metrics = 'cpu_ratio_gauge{resource_id="vm-1"} 42 1700000000123'
    base_params = {
        "host": "10.0.0.1",
        "model_id": "sangfor",
        "collection_task_id": "task-1",
        "collection_target": "vm-1",
        "collection_plugin_ref": "sangfor.info",
    }

    first = nats_helper.convert_prometheus_to_influx(
        metrics,
        {
            **base_params,
            "collection_result_id": "result-attempt-a",
            "collection_fence": 1,
        },
    )[0]
    second = nats_helper.convert_prometheus_to_influx(
        metrics,
        {
            **base_params,
            "collection_result_id": "result-attempt-b",
            "collection_fence": 2,
        },
    )[0]

    assert _series_key(first) == _series_key(second)
    assert "collection_result_id=" not in first
    assert "collection_fence=" not in first


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


@pytest.mark.parametrize(
    "metrics_data",
    (
        "metric_name{label=no_opening_quote} 1",
        "metric_name 1 not-a-timestamp",
    ),
)
def test_prometheus_conversion_rejects_malformed_labels_and_timestamps(metrics_data):
    with pytest.raises(nats_helper.MetricFormatError):
        nats_helper.convert_prometheus_to_influx(metrics_data, {"model_id": "network"})


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
async def test_metrics_batch_rejects_malformed_target_before_any_of_its_lines_reach_nats(monkeypatch):
    published = []

    async def publish_lines(_subject, lines, **_kwargs):
        published.extend(lines)
        return len(lines)

    monkeypatch.setattr(nats_helper, "nats_publish_lines", publish_lines)
    outcomes = await nats_helper.publish_metrics_batch_to_nats(
        (
            (
                {},
                "valid_metric 1",
                {"model_id": "network", "collection_result_id": "valid"},
                "run-1",
            ),
            (
                {},
                "would_be_valid 1\nmalformed_without_value",
                {"model_id": "network", "collection_result_id": "invalid"},
                "run-1",
            ),
        )
    )

    assert outcomes["valid"] is None
    assert isinstance(outcomes["invalid"], nats_helper.MetricFormatError)
    assert any(line.startswith("valid_metric,") for line in published)
    assert not any(line.startswith("would_be_valid,") for line in published)


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
async def test_successful_metrics_publish_is_debug_detail(monkeypatch):
    debug_logs = []

    async def publish_lines(_subject, lines):
        return len(lines)

    def capture_debug(message, *args):
        debug_logs.append(message % args if args else message)

    monkeypatch.setattr(nats_helper, "nats_publish_lines", publish_lines)
    monkeypatch.setattr(nats_helper.logger, "debug", capture_debug)

    published = await nats_helper._publish_lines_with_retry("metrics.snmp_facts", ["line-1", "line-2"], "run-snmp-1")

    assert published == 2
    assert len(debug_logs) == 1
    assert "event=nats_metrics_publish_succeeded" in debug_logs[0]
    assert "task_id=run-snmp-1" in debug_logs[0]
    assert "subject=metrics.snmp_facts" in debug_logs[0]
    assert "NATS指标推送成功" in debug_logs[0]
    assert "成功行数=2/2" in debug_logs[0]


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
async def test_metrics_transport_refuses_silent_core_nats_fallback(monkeypatch):
    monkeypatch.setenv("NATS_METRICS_JETSTREAM_ENABLED", "false")
    monkeypatch.setenv("NATS_METRICS_CORE_FALLBACK_ENABLED", "false")

    with pytest.raises(nats_utils.MetricsJetStreamRequiredError):
        await nats_utils.nats_publish_lines("metrics.network", ["line"])


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
async def test_metrics_jetstream_mode_waits_for_pubacks_with_stable_message_ids(
    monkeypatch,
):
    published = []

    class FakeJetStream:
        async def publish_async(self, subject, payload=b"", *, headers=None, stream=None, **_kwargs):
            published.append((subject, payload, dict(headers), stream))
            future = asyncio.get_running_loop().create_future()
            future.set_result(SimpleNamespace(stream="CMDB_METRICS", seq=len(published)))
            return future

    class FakeNats:
        is_connected = True
        is_closed = False
        is_reconnecting = False

        def jetstream(self, **_kwargs):
            return FakeJetStream()

        async def publish(self, *_args, **_kwargs):
            raise AssertionError("JetStream mode must not use Core NATS publish")

    async def get_nats(channel="control"):
        assert channel == "metrics"
        return FakeNats()

    monkeypatch.setenv("NATS_METRICS_JETSTREAM_ENABLED", "true")
    monkeypatch.setenv("NATS_JS_PUBLISH_MAX_PENDING", "4")
    monkeypatch.setenv("NATS_JS_PUBLISH_MAX_PENDING_BYTES", "1024")
    monkeypatch.setenv("NATS_JS_STREAM_NAME", "CMDB_METRICS")
    monkeypatch.setattr(nats_utils, "get_shared_nats", get_nats)
    monkeypatch.setattr(nats_utils, "_metrics_js_window", None)
    monkeypatch.setattr(nats_utils, "_metrics_js_context", None)
    monkeypatch.setattr(nats_utils, "_metrics_js_connection", None)

    count = await nats_utils.nats_publish_lines(
        "metrics.network",
        ["line-1", "line-2"],
        message_ids=["result-1:0", "result-1:1"],
    )

    assert count == 2
    assert [item[2]["Nats-Msg-Id"] for item in published] == [
        "result-1:0",
        "result-1:1",
    ]
    assert [item[3] for item in published] == ["CMDB_METRICS", "CMDB_METRICS"]


@pytest.mark.asyncio
async def test_metrics_batch_builds_result_scoped_stable_message_ids(monkeypatch):
    calls = []

    def iter_lines(_metrics, params):
        yield f"line-{params['collection_result_id']}-0"
        yield f"line-{params['collection_result_id']}-1"

    async def publish_lines(subject, lines, *, before_publish=None, message_ids=None):
        calls.append((subject, tuple(lines), tuple(message_ids or ())))
        return len(lines)

    monkeypatch.setenv("NATS_METRICS_JETSTREAM_ENABLED", "true")
    monkeypatch.setattr(nats_helper, "_iter_metrics_to_influx", iter_lines)
    monkeypatch.setattr(nats_helper, "nats_publish_lines", publish_lines)

    await nats_helper.publish_metrics_batch_to_nats(
        (
            (
                {},
                "a",
                {"model_id": "network", "collection_result_id": "result-a"},
                "run-1",
            ),
            (
                {},
                "b",
                {"model_id": "network", "collection_result_id": "result-b"},
                "run-1",
            ),
        )
    )

    assert len(calls) == 1
    message_ids = calls[0][2]
    assert len(message_ids) == len(set(message_ids)) == 4
    assert message_ids[0] != message_ids[2]
    assert all(len(message_id) == 64 for message_id in message_ids)


@pytest.mark.asyncio
async def test_direct_metrics_publish_message_ids_are_stable_per_result_and_distinct_across_runs(monkeypatch):
    published_message_ids = []

    async def publish_lines(_subject, lines, *, message_ids=None, **_kwargs):
        published_message_ids.append(tuple(message_ids or ()))
        return len(lines)

    monkeypatch.setenv("NATS_METRICS_JETSTREAM_ENABLED", "true")
    monkeypatch.setattr(nats_helper, "nats_publish_lines", publish_lines)
    params = {"model_id": "host", "collection_result_id": "result-a"}

    await nats_helper.publish_metrics_to_nats({}, "cpu_usage 1", params, "run-a")
    await nats_helper.publish_metrics_to_nats({}, "cpu_usage 1", params, "run-a")
    await nats_helper.publish_metrics_to_nats(
        {},
        "cpu_usage 1",
        {"model_id": "host", "collection_result_id": "result-b"},
        "run-b",
    )

    assert published_message_ids[0] == published_message_ids[1]
    assert published_message_ids[0] != published_message_ids[2]
    assert len(published_message_ids[0]) == 1


@pytest.mark.asyncio
async def test_direct_metrics_publish_validates_whole_result_before_first_nats_message(monkeypatch):
    published = []

    async def publish_lines(_subject, lines, **_kwargs):
        published.extend(lines)
        return len(lines)

    monkeypatch.setattr(nats_helper, "MAX_NATS_LINES_PER_FLUSH", 1)
    monkeypatch.setattr(nats_helper, "nats_publish_lines", publish_lines)

    with pytest.raises(nats_helper.MetricFormatError):
        await nats_helper.publish_metrics_to_nats(
            {},
            "valid_metric 1\nsecond_valid_metric 2\nmalformed_without_value",
            {"model_id": "host", "collection_result_id": "result-a"},
            "run-a",
        )

    assert published == []


@pytest.mark.asyncio
async def test_metrics_batch_keeps_confirmed_target_success_when_peer_puback_fails(monkeypatch):
    class PartiallyFailingJetStream:
        async def publish_async(self, _subject, payload=b"", **_kwargs):
            future = asyncio.get_running_loop().create_future()
            if payload == b"line-second":
                future.set_exception(RuntimeError("stream rejected second target"))
            else:
                future.set_result(SimpleNamespace(stream="CMDB_METRICS", seq=1))
            return future

    class FakeNats:
        is_connected = True
        is_closed = False
        is_reconnecting = False

        def jetstream(self, **_kwargs):
            return PartiallyFailingJetStream()

    async def get_nats(channel="control"):
        assert channel == "metrics"
        return FakeNats()

    def iter_lines(_metrics, params):
        yield f"line-{params['collection_result_id']}"

    monkeypatch.setenv("NATS_METRICS_JETSTREAM_ENABLED", "true")
    monkeypatch.setenv("NATS_JS_PUBLISH_MAX_ATTEMPTS", "1")
    monkeypatch.setattr(nats_utils, "get_shared_nats", get_nats)
    monkeypatch.setattr(nats_utils, "_metrics_js_window", None)
    monkeypatch.setattr(nats_utils, "_metrics_js_context", None)
    monkeypatch.setattr(nats_utils, "_metrics_js_connection", None)
    monkeypatch.setattr(nats_helper, "_iter_metrics_to_influx", iter_lines)

    metrics = CollectionMetrics()
    outcomes = await nats_helper.publish_metrics_batch_to_nats(
        (
            ({}, "a", {"model_id": "network", "collection_result_id": "first"}, "run-1"),
            ({}, "b", {"model_id": "network", "collection_result_id": "second"}, "run-1"),
        ),
        metrics=metrics,
    )

    assert outcomes["first"] is None
    assert isinstance(outcomes["second"], nats_helper.MetricsPublishError)
    assert outcomes["second"].delivery_detected is True
    assert metrics.snapshot()["publish_lines_total"] == 1


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
async def test_metrics_readiness_requires_expected_stream_and_subject_coverage(monkeypatch):
    class FakeJetStream:
        def __init__(self, subjects):
            self.subjects = subjects

        async def stream_info(self, stream_name):
            assert stream_name == "CMDB_METRICS"
            return SimpleNamespace(config=SimpleNamespace(subjects=self.subjects))

    class FakeNats:
        is_connected = True

        def __init__(self, subjects):
            self.subjects = subjects

        def jetstream(self):
            return FakeJetStream(self.subjects)

    monkeypatch.setenv("NATS_METRICS_JETSTREAM_ENABLED", "true")
    monkeypatch.setenv("NATS_JS_STREAM_NAME", "CMDB_METRICS")
    monkeypatch.setenv("NATS_METRIC_TOPIC", "metrics")

    async def covered(_channel):
        return FakeNats(["metrics.>"])

    monkeypatch.setattr(nats_utils, "get_shared_nats", covered)
    assert await nats_utils.metrics_transport_ready() is True

    async def missing(_channel):
        return FakeNats(["events.>"])

    monkeypatch.setattr(nats_utils, "get_shared_nats", missing)
    assert await nats_utils.metrics_transport_ready() is False


@pytest.mark.asyncio
async def test_metrics_connection_pending_buffer_covers_jetstream_byte_window(monkeypatch):
    connected_options = {}

    class FakeConfig:
        servers = ["nats://nats:4222"]
        tls_enabled = False
        user = None

        def to_connect_options(self):
            return {"pending_size": 2 * 1024 * 1024}

    class FakeNats:
        is_connected = False
        is_reconnecting = False
        is_closed = True

        async def connect(self, **options):
            connected_options.update(options)
            self.is_connected = True
            self.is_closed = False

    monkeypatch.setenv("NATS_JS_PUBLISH_MAX_PENDING_BYTES", str(32 * 1024 * 1024))
    monkeypatch.delenv("NATS_METRICS_PENDING_SIZE_BYTES", raising=False)
    monkeypatch.setattr(nats_utils.NATSConfig, "from_env", lambda **_kwargs: FakeConfig())
    monkeypatch.setattr(nats_utils, "NATS", FakeNats)
    monkeypatch.setattr(nats_utils, "_metrics_nc", None)
    monkeypatch.setattr(nats_utils, "_metrics_connect_lock", None)

    await nats_utils.get_shared_nats("metrics")

    assert connected_options["pending_size"] >= 32 * 1024 * 1024


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
        "nats_js_publish_pending_messages": 0,
        "nats_js_publish_pending_bytes": 0,
        "nats_js_publish_waiting_messages": 0,
        "nats_js_publish_waiting_bytes": 0,
        "nats_js_publish_pending_messages_peak": 0,
        "nats_js_publish_pending_bytes_peak": 0,
        "nats_js_publish_waiting_messages_peak": 0,
        "nats_js_publish_waiting_bytes_peak": 0,
        "nats_js_publish_confirmed_total": 0,
        "nats_js_puback_duration_seconds_p95": 0.0,
        "nats_js_puback_duration_seconds_p99": 0.0,
        "nats_js_puback_timeout_total": 0,
        "nats_js_publish_retry_total": 0,
        "nats_js_publish_rejected_total": 0,
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
