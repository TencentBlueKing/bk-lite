"""失败日志用实际发布链路验证；只替换外部 JetStream。"""

import asyncio
import logging
from collections import Counter
from types import SimpleNamespace

import pytest
from core.collection.contracts import TargetExecutorSettings
from core.collection.metrics import CollectionMetrics
from core.collection.result_delivery import ResultDeliveryCoordinator
from core.collection.result_publisher import BufferedResultPublisher, NatsResultPublisher
from core.infra import nats_utils
from core.infra.jetstream_publish_window import JetStreamMessage, JetStreamPublishWindow, JetStreamPublishWindowSettings, JetStreamWindowPublishError
from core.infra.publish_budget import PublishBudget

from scripts.benchmark_jetstream_publisher import _request_and_lease, network_results


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["connect", "publish_call", "puback", "total_budget", "success"])
@pytest.mark.parametrize("plugin_ref", ["network.config", "network_topo.config"])
async def test_failure_details_preserve_progress_and_distinguish_timeout(monkeypatch, caplog, failure, plugin_ref):
    seen = set()
    sentinel = "NEVER_LOG_PAYLOAD_OR_CREDENTIAL"

    class JetStream:
        async def publish_async(self, subject, payload, **kwargs):
            message_id = kwargs["headers"]["Nats-Msg-Id"]
            seen.add(message_id)
            if failure == "publish_call":
                await asyncio.sleep(10)
            future = asyncio.get_running_loop().create_future()
            if failure == "success" or (failure in {"puback", "total_budget"} and len(seen) <= 64):
                future.set_result(None)
            return future

    async def provider():
        if failure == "connect":
            await asyncio.sleep(10)
        return JetStream()

    window = JetStreamPublishWindow(
        provider,
        settings=JetStreamPublishWindowSettings(puback_timeout_seconds=0.015 if failure != "total_budget" else 1, max_attempts=1),
    )
    monkeypatch.setattr(nats_utils, "_metrics_js_window", window)
    test_logger = logging.getLogger("test.publish.failure.details")
    monkeypatch.setattr("core.collection.result_delivery.logger", test_logger)
    publisher = BufferedResultPublisher(NatsResultPublisher(), capacity=1)
    request, lease = _request_and_lease(task_id=sentinel, plugin_ref=plugin_ref, targets=("192.0.2.1",))
    coordinator = ResultDeliveryCoordinator(
        publisher=publisher,
        settings=TargetExecutorSettings(publish_total_timeout_seconds=0.06 if failure == "total_budget" else 120),
        metrics=CollectionMetrics(),
        request=request,
        lease=lease,
        log_identity="instance_id=test",
        failure_log_limit=0,
    )
    try:
        with caplog.at_level(logging.WARNING, logger=test_logger.name):
            result = next(network_results(devices=1, lines_per_device=130))
            for row in result.value.data["network_device"]:
                row["description"] = sentinel
            pending = await coordinator.enqueue(0, result)
            terminal = await asyncio.wait_for(coordinator.finish(pending), 2)
        details = pending.receipt.publish_diagnostics
        assert details["total_lines"] == 130
        assert details["total_bytes"] > 0
        records = [r for r in caplog.records if r.name == test_logger.name]
        if failure == "success":
            assert terminal == (0, "succeeded", "")
            assert details["confirmed_lines"] == details["attempted_lines"] == 130
            assert not records
        else:
            assert len(records) == 1  # 网络失败不受前三条摘要限制。
            record = records[0]
            assert record.args and "%s" in record.msg and not record.exc_info
            message = logging.Formatter().format(record)
            assert sentinel not in message and sentinel not in repr(record.args)
            assert "task_id=" not in message and "attempt_id=" not in message
            assert "retries=0 " in message
            assert f"confirmed={details['confirmed_lines']} " in message
            assert f"attempted={details['attempted_lines']} " in message
            assert f"target={pending.target}" in message
            assert "timeout_seconds=120" not in message
            assert f"timeout_kind={'total_budget' if failure == 'total_budget' else 'attempt'}" in message
            assert details["failed_stage"] == ("puback" if failure == "total_budget" else failure)
            assert details["error_type"] == "TimeoutError"
            assert details["confirmed_lines"] == (64 if failure in {"puback", "total_budget"} else 0)
            assert details["attempted_lines"] == len(seen)
            assert details[f"{details['failed_stage']}_ms"] > 0
            assert details["send_ms"] > 0
            assert terminal[1] in {"unknown", "failed"}
        assert window.snapshot().pending_messages == publisher.pending_payloads == 0
    finally:
        await publisher.shutdown()


@pytest.mark.asyncio
async def test_retry_counts_unique_messages_and_preserves_protocol_and_error_identity():
    attempts = Counter()
    original_error = ConnectionError("DO_NOT_LOG_RESPONSE_BODY")
    calls = []

    class JetStream:
        async def publish_async(self, subject, payload, **kwargs):
            message_id = kwargs["headers"]["Nats-Msg-Id"]
            attempts[message_id] += 1
            calls.append((subject, payload, kwargs))
            future = asyncio.get_running_loop().create_future()
            if message_id == "bad" or attempts[message_id] == 1:
                future.set_exception(original_error)
            else:
                future.set_result(None)
            return future

    budget = PublishBudget(120)
    window = JetStreamPublishWindow(lambda: JetStream(), settings=JetStreamPublishWindowSettings(max_attempts=2))
    assert await window.publish("metrics.network", [JetStreamMessage(b"payload", "good", budget=budget)]) == 1
    with pytest.raises(JetStreamWindowPublishError) as caught:
        await window.publish("metrics.network", [JetStreamMessage(b"payload", "bad", budget=budget)])
    assert caught.value.error is original_error
    assert str(original_error) == "DO_NOT_LOG_RESPONSE_BODY"
    assert budget.attempted_lines == 2
    assert budget.confirmed_lines == 1
    assert budget.retry_count == 2
    assert attempts == {"good": 2, "bad": 2}
    assert all(subject == "metrics.network" and payload == b"payload" for subject, payload, _ in calls)
    assert [kwargs["headers"] for _, _, kwargs in calls] == [
        {"Nats-Msg-Id": "good"},
        {"Nats-Msg-Id": "good"},
        {"Nats-Msg-Id": "bad"},
        {"Nats-Msg-Id": "bad"},
    ]
    assert "DO_NOT_LOG_RESPONSE_BODY" not in repr(original_error.publish_diagnostics)
    assert original_error.publish_diagnostics["timeout_kind"] == "-"
    assert window.snapshot().pending_messages == window.snapshot().pending_bytes == 0


@pytest.mark.asyncio
async def test_send_deadline_uses_event_loop_clock_even_when_monotonic_epoch_differs(monkeypatch):
    from core.infra import publish_budget

    monotonic = publish_budget.time.monotonic
    monkeypatch.setattr(publish_budget, "time", SimpleNamespace(monotonic=lambda: monotonic() - 3600))
    calls = []

    class JetStream:
        async def publish_async(self, *_args, **_kwargs):
            calls.append(True)
            future = asyncio.get_running_loop().create_future()
            future.set_result(None)
            return future

    budget = PublishBudget(120)
    window = JetStreamPublishWindow(lambda: JetStream())
    assert await window.publish("metrics.network", [JetStreamMessage(b"payload", "clock-test", budget=budget)]) == 1
    assert calls == [True]
    assert budget.remaining > 119
    assert window.snapshot().deadline_expired_total == 0


@pytest.mark.asyncio
async def test_receipt_terminal_timestamp_uses_same_clock_as_delivery_start(monkeypatch):
    from core.collection import result_publisher

    monotonic = result_publisher.time.monotonic
    monkeypatch.setattr(result_publisher, "time", SimpleNamespace(monotonic=lambda: monotonic() - 3600))
    loop = asyncio.get_running_loop()
    started = loop.time()
    completion = loop.create_future()
    receipt = result_publisher.FuturePublishReceipt(completion)
    completion.set_result(None)
    await asyncio.sleep(0)
    assert started <= receipt.terminal_at <= loop.time()
