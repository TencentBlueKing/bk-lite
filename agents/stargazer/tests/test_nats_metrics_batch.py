import asyncio
import time

import pytest
from core.collection.contracts import StructuredMetricsPayload
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

    monkeypatch.setattr(nats_helper, "convert_prometheus_to_influx", convert)
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

    monkeypatch.setattr(nats_helper, "convert_prometheus_to_influx", convert)
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

    assert isinstance(outcomes["network-1"], TimeoutError)
    assert outcomes["mysql-1"] is None


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

    monkeypatch.setattr(nats_helper, "convert_prometheus_to_influx", convert)
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
async def test_nats_connection_failure_is_marked_as_not_delivered(monkeypatch):
    async def connection_failed():
        raise ConnectionError("connect failed")

    monkeypatch.setattr(nats_utils, "get_shared_nats", connection_failed)

    with pytest.raises(nats_utils.NatsLinesPublishError) as error:
        await nats_utils.nats_publish_lines("metrics.network", ["line"])

    assert error.value.attempted_count_before_failure == 0
    assert error.value.delivery_detected is False


@pytest.mark.asyncio
async def test_large_metrics_encoding_does_not_block_event_loop(monkeypatch):
    ticks = 0

    def slow_convert(_metrics, _params):
        time.sleep(0.05)
        return ["line"]

    async def publish(_subject, lines, _task_id):
        return len(lines)

    async def heartbeat():
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.005)

    monkeypatch.setattr(nats_helper, "convert_prometheus_to_influx", slow_convert)
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
