"""真实发布链路的公平调度回归；只替换外部 JetStream 服务。"""

import asyncio
import gc
import threading
import weakref
from dataclasses import replace

import pytest
from core.collection.contracts import StructuredMetricsPayload, TargetCollectionResult, TargetExecutorSettings
from core.collection.metrics import CollectionMetrics
from core.collection.result_delivery import ResultDeliveryCoordinator
from core.collection.result_publisher import BufferedResultPublisher, NatsResultPublisher
from core.infra import nats_utils
from core.infra.jetstream_publish_window import JetStreamMessage, JetStreamPublishWindow, JetStreamPublishWindowSettings, JetStreamWindowPublishError

from scripts.benchmark_jetstream_publisher import _request_and_lease, network_results


@pytest.mark.asyncio
async def test_credit_queue_longer_than_send_budget_still_delivers(monkeypatch):
    """占满唯一信贷后排队超过发送预算，未发送目标仍应等待并在恢复后成功。"""
    jetstream = GatedJetStream()
    window = JetStreamPublishWindow(lambda: jetstream, settings=JetStreamPublishWindowSettings(max_pending_messages=1))
    monkeypatch.setattr(nats_utils, "_metrics_js_window", window)
    holder = asyncio.create_task(window.publish("metrics.large", [JetStreamMessage(b"holder", "holder")]))
    await jetstream.first_chunk.wait()
    publisher = BufferedResultPublisher(NatsResultPublisher(), capacity=1)
    request, lease = _request_and_lease(task_id="small", plugin_ref="small", targets=("b",))
    delivery = ResultDeliveryCoordinator(
        publisher=publisher,
        settings=TargetExecutorSettings(publish_total_timeout_seconds=0.1, publish_queue_timeout_seconds=0.05),
        metrics=CollectionMetrics(),
        request=request,
        lease=lease,
        log_identity="queue-budget",
        failure_log_limit=3,
    )
    try:
        pending = await delivery.enqueue(0, next(network_results(devices=1, lines_per_device=1)))
        finishing = asyncio.create_task(delivery.finish(pending))
        async with asyncio.timeout(2):
            while window.snapshot().waiting_messages == 0:
                await asyncio.sleep(0.001)
        await asyncio.sleep(0.2)
        assert not finishing.done(), "排队不应消耗发送预算"
        assert not pending.receipt.delivery_started
        jetstream.release.set()
        await holder
        assert await asyncio.wait_for(finishing, 2) == (0, "succeeded", "")
        assert pending.receipt.queue_residence_seconds >= 0.2
        assert pending.receipt.credit_wait_seconds >= 0.2
        assert pending.receipt.delivery_duration_seconds < 0.1
    finally:
        jetstream.release.set()
        await holder
        await publisher.shutdown()
    assert publisher.pending_payloads == window.snapshot().pending_messages == 0


class GatedJetStream:
    def __init__(self):
        self.first_chunk = asyncio.Event()
        self.release = asyncio.Event()
        self.large_lines = 0
        self.small_after_lines = None

    async def publish_async(self, subject, payload, **kwargs):
        future = asyncio.get_running_loop().create_future()
        if "small" in subject:
            self.small_after_lines = self.large_lines
            future.set_result(None)
        else:
            self.large_lines += 1
            self.first_chunk.set()

            async def confirm():
                await self.release.wait()
                if not future.done():
                    future.set_result(None)

            asyncio.create_task(confirm())
        return future


@pytest.mark.asyncio
@pytest.mark.parametrize("lines, expected", [(64, "succeeded"), (192, "unknown")])
async def test_parallel_acks_share_budget_but_chunks_do_not_reset_it(monkeypatch, lines, expected):
    from scripts.benchmark_publish_fairness import DelayedJetStream

    window = JetStreamPublishWindow(
        lambda: DelayedJetStream(0.06), settings=JetStreamPublishWindowSettings(max_pending_messages_per_call=64, max_attempts=1)
    )
    monkeypatch.setattr(nats_utils, "_metrics_js_window", window)
    publisher = BufferedResultPublisher(NatsResultPublisher(), capacity=1)
    request, lease = _request_and_lease(task_id="budget", plugin_ref="network", targets=("a",))
    delivery = ResultDeliveryCoordinator(
        publisher=publisher,
        settings=TargetExecutorSettings(publish_total_timeout_seconds=0.14),
        metrics=CollectionMetrics(),
        request=request,
        lease=lease,
        log_identity="budget",
        failure_log_limit=3,
    )
    try:
        pending = await delivery.enqueue(0, next(network_results(devices=1, lines_per_device=lines)))
        terminal = await asyncio.wait_for(delivery.finish(pending), 2)
        assert terminal[1] == expected
        if expected == "succeeded":
            assert window.snapshot().confirmed_total == 64
            assert pending.receipt.delivery_duration_seconds < 0.14
        else:
            assert window.snapshot().confirmed_total == 128
            assert 0.14 <= pending.receipt.delivery_duration_seconds < 0.2
    finally:
        await publisher.shutdown()
    assert window.snapshot().pending_messages == publisher.pending_payloads == 0


@pytest.mark.asyncio
async def test_run_observes_fast_terminal_and_releases_payload_behind_four_slow_receipts(monkeypatch):
    from core.collection.run_result_sink import RunResultSink

    jetstream = GatedJetStream()
    monkeypatch.setattr(nats_utils, "_metrics_js_window", JetStreamPublishWindow(lambda: jetstream))
    publisher = BufferedResultPublisher(NatsResultPublisher(), capacity=5)
    request, lease = _request_and_lease(task_id="large", plugin_ref="large", targets=("a",))
    metrics = CollectionMetrics()
    delivery = ResultDeliveryCoordinator(
        publisher=publisher,
        settings=TargetExecutorSettings(),
        metrics=metrics,
        request=request,
        lease=lease,
        log_identity="observer",
        failure_log_limit=3,
    )
    small_request = replace(request, plugin_ref="small", params={**request.params, "model_id": "small", "monitor_type": "small"})
    small_delivery = ResultDeliveryCoordinator(
        publisher=publisher,
        settings=TargetExecutorSettings(),
        metrics=metrics,
        request=small_request,
        lease=lease,
        log_identity="observer",
        failure_log_limit=3,
    )
    sink = RunResultSink(delivery=delivery, metrics=metrics, total_targets=5)
    try:
        for i in range(4):
            await sink.accept(await delivery.enqueue(i, next(network_results(devices=1, lines_per_device=1))))
        await jetstream.first_chunk.wait()
        payload = StructuredMetricsPayload(data={"network": [{"ip": "small"}]})
        ref = weakref.ref(payload)
        pending = await small_delivery.enqueue(4, TargetCollectionResult(target="small", status="success", attempts=1, value=payload))
        del payload
        await sink.accept(pending)
        await asyncio.wait_for(pending.receipt.wait(), 2)
        for _ in range(10):
            await asyncio.sleep(0)
        assert sink.pending_deliveries == 4, "已完成回执不能被前四个慢回执挡住"
        gc.collect()
        assert ref() is None, "即使 Scheduler/Executor 保留 Pending，也不得保留已转交的 payload"
        jetstream.release.set()
        assert (await sink.finish()).summary.publish_succeeded == 5
    finally:
        jetstream.release.set()
        await sink.abort()
        await publisher.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("failures, expected", [(1, "succeeded"), (2, "failed")])
async def test_metadata_retry_keeps_payload_and_never_reports_unsent_metrics_unknown(monkeypatch, failures, expected):
    class Store:
        calls = 0

        async def save(self, envelope):
            self.calls += 1
            if self.calls <= failures:
                raise ConnectionError("sensitive-metadata-response")

    from scripts.benchmark_publish_fairness import DelayedJetStream

    store = Store()
    window = JetStreamPublishWindow(lambda: DelayedJetStream(0.001))
    monkeypatch.setattr(nats_utils, "_metrics_js_window", window)
    publisher = BufferedResultPublisher(NatsResultPublisher(round_metadata_store=store), capacity=1)
    request, lease = _request_and_lease(task_id="metadata", plugin_ref="pc", targets=("a",))
    delivery = ResultDeliveryCoordinator(
        publisher=publisher,
        settings=TargetExecutorSettings(),
        metrics=CollectionMetrics(),
        request=request,
        lease=lease,
        log_identity="metadata",
        failure_log_limit=3,
    )
    payload = StructuredMetricsPayload(
        data={"pc": [{"inst_name": "host"}]},
        round_metadata={"snapshot_id": "one", "snapshot_status": "complete", "details": {"software_expected_count": 0, "software_error_count": 0}},
    )
    try:
        pending = await delivery.enqueue(0, TargetCollectionResult(target="a", status="success", attempts=1, value=payload))
        assert (await delivery.finish(pending))[1] == expected
        assert store.calls == 2
        assert pending.receipt.delivery_started == (expected == "succeeded")
        assert window.snapshot().confirmed_total == (1 if expected == "succeeded" else 0)
    finally:
        await publisher.shutdown()
    assert publisher.pending_payloads == 0


@pytest.mark.asyncio
async def test_shutdown_cooperatively_stops_large_encoding_before_releasing_payload(monkeypatch):
    import time

    from scripts.benchmark_publish_fairness import DelayedJetStream

    entered = threading.Event()

    class SlowRow(dict):
        def items(self):
            entered.set()
            time.sleep(0.002)
            return super().items()

    window = JetStreamPublishWindow(lambda: DelayedJetStream(0.001))
    monkeypatch.setattr(nats_utils, "_metrics_js_window", window)
    publisher = BufferedResultPublisher(NatsResultPublisher(), capacity=1)
    request, lease = _request_and_lease(task_id="cancel-encode", plugin_ref="network", targets=("a",))
    payload = StructuredMetricsPayload(data={"network": [SlowRow(ip=f"target-{i}") for i in range(400)]})
    ref = weakref.ref(payload)
    receipt = await publisher.enqueue(request, TargetCollectionResult(target="a", status="success", attempts=1, value=payload), lease)
    del payload
    while not entered.is_set():
        await asyncio.sleep(0.001)
    started = time.monotonic()
    await publisher.shutdown(grace_seconds=0.01)
    assert time.monotonic() - started < 0.25
    gc.collect()
    assert ref() is None
    assert receipt.done()
    assert window.snapshot().confirmed_total == publisher.pending_payloads == 0


@pytest.mark.asyncio
async def test_invalid_encoding_is_permanent_and_reports_encode_stage_without_payload(monkeypatch, caplog):
    from scripts.benchmark_publish_fairness import DelayedJetStream

    window = JetStreamPublishWindow(lambda: DelayedJetStream(0.001))
    monkeypatch.setattr(nats_utils, "_metrics_js_window", window)
    publisher = BufferedResultPublisher(NatsResultPublisher(), capacity=1)
    request, lease = _request_and_lease(task_id="invalid", plugin_ref="network", targets=("a",))
    delivery = ResultDeliveryCoordinator(
        publisher=publisher,
        settings=TargetExecutorSettings(),
        metrics=CollectionMetrics(),
        request=request,
        lease=lease,
        log_identity="invalid",
        failure_log_limit=3,
    )
    try:
        pending = await delivery.enqueue(
            0,
            TargetCollectionResult(
                target="a",
                status="success",
                attempts=1,
                value=StructuredMetricsPayload(data={"network": [{"description": "secret-payload-sentinel" + "x" * 910_000}]}),
            ),
        )
        assert (await delivery.finish(pending))[1] == "permanent_failed"
        assert pending.receipt.failed_stage == "encode"
        record = next(r for r in caplog.records if "event=result_publish_failed" in r.msg)
        assert "%s" in record.msg and record.args
        assert "phase=encode" in record.getMessage()
        assert "secret-payload-sentinel" not in caplog.text
        assert not record.exc_info
        assert window.snapshot().confirmed_total == 0
    finally:
        await publisher.shutdown()


@pytest.mark.asyncio
async def test_small_result_reuses_validated_encoding_without_retraversing_rows(monkeypatch):
    from scripts.benchmark_publish_fairness import DelayedJetStream

    class CountedRow(dict):
        reads = 0

        def items(self):
            self.reads += 1
            return super().items()

    rows = [CountedRow(ip=f"target-{i}") for i in range(128)]
    window = JetStreamPublishWindow(lambda: DelayedJetStream(0.001))
    monkeypatch.setattr(nats_utils, "_metrics_js_window", window)
    publisher = BufferedResultPublisher(NatsResultPublisher(), capacity=1)
    request, lease = _request_and_lease(task_id="encode-once", plugin_ref="network", targets=("a",))
    try:
        receipt = await publisher.enqueue(
            request, TargetCollectionResult(target="a", status="success", attempts=1, value=StructuredMetricsPayload(data={"network": rows})), lease
        )
        await receipt.wait()
        assert window.snapshot().confirmed_total == 128
        assert all(row.reads == 1 for row in rows)
    finally:
        await publisher.shutdown()


@pytest.mark.asyncio
async def test_connection_failure_before_sdk_send_is_failed_not_unknown(monkeypatch):
    async def unavailable():
        raise ConnectionError("sensitive-connection-response")

    window = JetStreamPublishWindow(unavailable)
    monkeypatch.setattr(nats_utils, "_metrics_js_window", window)
    publisher = BufferedResultPublisher(NatsResultPublisher(), capacity=1)
    request, lease = _request_and_lease(task_id="unavailable", plugin_ref="network", targets=("a",))
    delivery = ResultDeliveryCoordinator(
        publisher=publisher,
        settings=TargetExecutorSettings(),
        metrics=CollectionMetrics(),
        request=request,
        lease=lease,
        log_identity="unavailable",
        failure_log_limit=3,
    )
    try:
        pending = await delivery.enqueue(0, next(network_results(devices=1, lines_per_device=1)))
        assert (await delivery.finish(pending))[1] == "failed"
        assert not pending.receipt.delivery_started
        assert window.snapshot().retry_total == 1
        assert window.snapshot().confirmed_total == 0
    finally:
        await publisher.shutdown()


@pytest.mark.asyncio
async def test_credit_wait_between_chunks_pauses_the_same_target_budget(monkeypatch):
    from scripts.benchmark_publish_fairness import DelayedJetStream

    holder_tasks = []

    class BetweenChunks(DelayedJetStream):
        async def publish_async(self, subject, payload, **kwargs):
            future = await super().publish_async(subject, payload, **kwargs)
            if self.count == 1:
                future.add_done_callback(
                    lambda _: holder_tasks.append(
                        asyncio.create_task(window.publish("benchmark.credit-holder", [JetStreamMessage(b"holder", "between-chunks")]))
                    )
                )
            return future

    monkeypatch.setenv("NATS_JS_PUBLISH_MAX_PENDING_PER_CALL", "1")
    jetstream = BetweenChunks(0.03, credit_pause_seconds=0.25)
    window = JetStreamPublishWindow(lambda: jetstream, settings=JetStreamPublishWindowSettings(max_pending_messages=1))
    monkeypatch.setattr(nats_utils, "_metrics_js_window", window)
    publisher = BufferedResultPublisher(NatsResultPublisher(), capacity=1)
    request, lease = _request_and_lease(task_id="between", plugin_ref="network", targets=("a",))
    delivery = ResultDeliveryCoordinator(
        publisher=publisher,
        settings=TargetExecutorSettings(publish_total_timeout_seconds=0.1),
        metrics=CollectionMetrics(),
        request=request,
        lease=lease,
        log_identity="between",
        failure_log_limit=3,
    )
    try:
        pending = await delivery.enqueue(0, next(network_results(devices=1, lines_per_device=2)))
        assert await asyncio.wait_for(delivery.finish(pending), 2) == (0, "succeeded", "")
        assert pending.receipt.delivery_duration_seconds < 0.1
        assert pending.receipt.credit_wait_seconds >= 0.2
    finally:
        await asyncio.gather(*holder_tasks)
        await publisher.shutdown()


@pytest.mark.asyncio
async def test_explicit_core_fallback_uses_shared_send_budget_and_marks_delivery(monkeypatch):
    class CoreNats:
        async def publish(self, subject, payload):
            return None

        async def flush(self, **kwargs):
            await asyncio.sleep(0.04)

    async def connected(_channel):
        return CoreNats()

    monkeypatch.setenv("NATS_METRICS_JETSTREAM_ENABLED", "false")
    monkeypatch.setenv("NATS_METRICS_CORE_FALLBACK_ENABLED", "true")
    monkeypatch.setattr(nats_utils, "get_shared_nats", connected)
    publisher = BufferedResultPublisher(NatsResultPublisher(), capacity=1)
    request, lease = _request_and_lease(task_id="fallback", plugin_ref="network", targets=("a",))
    delivery = ResultDeliveryCoordinator(
        publisher=publisher,
        settings=TargetExecutorSettings(publish_total_timeout_seconds=0.05),
        metrics=CollectionMetrics(),
        request=request,
        lease=lease,
        log_identity="fallback",
        failure_log_limit=3,
    )
    try:
        pending = await delivery.enqueue(0, next(network_results(devices=1, lines_per_device=128)))
        assert (await delivery.finish(pending))[1] == "unknown"
        assert pending.receipt.delivery_started
        assert 0.05 <= pending.receipt.delivery_duration_seconds < 0.12
        assert pending.receipt.failed_stage == "core_flush"
    finally:
        await publisher.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("budget, max_sent", [(1e-12, 0), (0.01, 1)])
async def test_core_fallback_does_not_send_after_budget_exhaustion_without_sdk_yield(monkeypatch, budget, max_sent):
    import time

    class CoreNats:
        sent = 0

        async def publish(self, subject, payload):
            self.sent += 1
            time.sleep(0.02)  # SDK 的 await 可能没有交回事件循环，不能只依赖 timeout 回调。

        async def flush(self, **kwargs):
            return None

    core = CoreNats()

    async def connected(_channel):
        return core

    monkeypatch.setenv("NATS_METRICS_JETSTREAM_ENABLED", "false")
    monkeypatch.setenv("NATS_METRICS_CORE_FALLBACK_ENABLED", "true")
    monkeypatch.setattr(nats_utils, "get_shared_nats", connected)
    publisher = BufferedResultPublisher(NatsResultPublisher(), capacity=1)
    request, lease = _request_and_lease(task_id="expired-core", plugin_ref="network", targets=("a",))
    delivery = ResultDeliveryCoordinator(
        publisher=publisher,
        settings=TargetExecutorSettings(publish_total_timeout_seconds=budget),
        metrics=CollectionMetrics(),
        request=request,
        lease=lease,
        log_identity="expired-core",
        failure_log_limit=3,
    )
    try:
        pending = await delivery.enqueue(0, next(network_results(devices=1, lines_per_device=64)))
        terminal = await delivery.finish(pending)
        assert core.sent <= max_sent
        assert terminal[1] == ("failed" if core.sent == 0 else "unknown")
    finally:
        await publisher.shutdown()


@pytest.mark.asyncio
async def test_new_small_result_gets_a_turn_before_large_result_finishes(monkeypatch):
    jetstream = GatedJetStream()
    window = JetStreamPublishWindow(lambda: jetstream, settings=JetStreamPublishWindowSettings(max_pending_messages_per_call=64))
    monkeypatch.setattr(nats_utils, "_metrics_js_window", window)
    publisher = BufferedResultPublisher(NatsResultPublisher(), capacity=2, batch_size=50, worker_count=1)
    large_request, large_lease = _request_and_lease(task_id="large", plugin_ref="large", targets=("a",))
    small_request, small_lease = _request_and_lease(task_id="small", plugin_ref="small", targets=("b",))
    try:
        large = await publisher.enqueue(large_request, next(network_results(devices=1, lines_per_device=1024)), large_lease)
        await asyncio.wait_for(jetstream.first_chunk.wait(), 2)
        small = await publisher.enqueue(small_request, next(network_results(devices=1, lines_per_device=1)), small_lease)
        jetstream.release.set()
        await asyncio.wait_for(small.wait(), 3)
        assert jetstream.small_after_lines <= 64
        await large.wait()
    finally:
        jetstream.release.set()
        await publisher.shutdown()
    assert publisher.pending_payloads == 0


@pytest.mark.asyncio
async def test_finished_payload_is_collectable_while_slow_peer_is_pending(monkeypatch):
    jetstream = GatedJetStream()
    monkeypatch.setattr(nats_utils, "_metrics_js_window", JetStreamPublishWindow(lambda: jetstream))
    publisher = BufferedResultPublisher(NatsResultPublisher(), capacity=2, worker_count=2)
    large_request, large_lease = _request_and_lease(task_id="large", plugin_ref="large", targets=("a",))
    small_request, small_lease = _request_and_lease(task_id="small", plugin_ref="small", targets=("b",))
    try:
        large = await publisher.enqueue(large_request, next(network_results(devices=1, lines_per_device=512)), large_lease)
        await asyncio.wait_for(jetstream.first_chunk.wait(), 2)
        result = next(network_results(devices=1, lines_per_device=1))
        reference = weakref.ref(result.value)
        small = await publisher.enqueue(small_request, result, small_lease)
        del result
        await asyncio.wait_for(small.wait(), 2)
        gc.collect()
        assert not large.done()
        assert reference() is None
        assert publisher.pending_payloads == 1
    finally:
        jetstream.release.set()
        await publisher.shutdown()


@pytest.mark.asyncio
async def test_first_send_wait_is_not_overwritten_by_later_lines(monkeypatch):
    jetstream = GatedJetStream()
    monkeypatch.setattr(nats_utils, "_metrics_js_window", JetStreamPublishWindow(lambda: jetstream))
    publisher = BufferedResultPublisher(NatsResultPublisher(), capacity=1)
    request, lease = _request_and_lease(task_id="large", plugin_ref="large", targets=("a",))
    try:
        receipt = await publisher.enqueue(request, next(network_results(devices=1, lines_per_device=512)), lease)
        await asyncio.wait_for(jetstream.first_chunk.wait(), 2)
        first_wait = receipt.queue_residence_seconds
        await asyncio.sleep(0.04)
        jetstream.release.set()
        await receipt.wait()
        assert receipt.queue_residence_seconds == first_wait
    finally:
        jetstream.release.set()
        await publisher.shutdown()


@pytest.mark.asyncio
async def test_managed_predelivery_failure_never_retries_released_payload():
    class BeforeDeliveryError(RuntimeError):
        delivery_detected = False

    class FailedReceipt:
        retries_managed = True

        async def wait(self):
            raise BeforeDeliveryError("service unavailable")

    class Publisher:
        async def enqueue(self, *args, **kwargs):
            return FailedReceipt()

    request, lease = _request_and_lease(task_id="managed", plugin_ref="network", targets=("a",))
    metrics = CollectionMetrics()
    coordinator = ResultDeliveryCoordinator(
        publisher=Publisher(),
        settings=TargetExecutorSettings(),
        metrics=metrics,
        request=request,
        lease=lease,
        log_identity="test",
        failure_log_limit=0,
    )
    pending = await coordinator.enqueue(0, next(network_results(devices=1, lines_per_device=1)))
    terminal = await coordinator.finish(replace(pending, result=None))
    assert terminal == (0, "failed", "BeforeDeliveryError")
    assert metrics.snapshot().get("result_publish_retry_total", 0) == 0


@pytest.mark.asyncio
async def test_failure_receipt_does_not_retain_payload_through_traceback():
    publisher = BufferedResultPublisher(NatsResultPublisher(), capacity=1)
    request, lease = _request_and_lease(task_id="bad-encoding", plugin_ref="network", targets=("a",))
    payload = StructuredMetricsPayload(data={"network": [{"description": "x" * 910_000}]})
    reference = weakref.ref(payload)
    receipt = await publisher.enqueue(request, TargetCollectionResult(target="a", status="success", attempts=1, value=payload), lease)
    del payload
    try:
        with pytest.raises(ValueError):
            await receipt.wait()
        gc.collect()
        assert reference() is None
        assert publisher.pending_payloads == 0
    finally:
        await publisher.shutdown()


@pytest.mark.asyncio
async def test_predelivery_total_deadline_log_uses_total_budget_not_queue_budget(monkeypatch):
    from core.collection.contracts import PublishOutcome, PublishStatus
    from core.collection.result_publisher import FuturePublishReceipt

    records = []
    monkeypatch.setattr("core.collection.result_delivery.logger.warning", lambda template, *args: records.append((template, args)))

    class Publisher:
        async def enqueue(self, *args, **kwargs):
            completion = asyncio.get_running_loop().create_future()
            completion.set_result(PublishOutcome(status=PublishStatus.RETRYABLE_FAILED, error_code="publish_total_timeout_before_delivery"))
            return FuturePublishReceipt(completion, retries_managed=True)

    request, lease = _request_and_lease(task_id="deadline-log", plugin_ref="network", targets=("a",))
    coordinator = ResultDeliveryCoordinator(
        publisher=Publisher(),
        settings=TargetExecutorSettings(),
        metrics=CollectionMetrics(),
        request=request,
        lease=lease,
        log_identity="run=log-test",
        failure_log_limit=1,
    )
    result = next(network_results(devices=1, lines_per_device=1))
    result = replace(result, value=StructuredMetricsPayload(data={"network": [{"secret": "PAYLOAD_SENTINEL"}]}))
    terminal = await coordinator.finish(await coordinator.enqueue(0, result))
    assert terminal == (0, "failed", "publish_total_timeout_before_delivery")
    assert len(records) == 1
    template, args = records[0]
    assert "timeout_seconds=%s" in template
    assert args[-1] == 120
    message = template % args
    assert "phase=before_delivery reason=publish_total_timeout_before_delivery" in message
    assert "timeout_seconds=120" in message
    assert "PAYLOAD_SENTINEL" not in message


@pytest.mark.asyncio
async def test_prometheus_exposes_presend_and_delivery_intervals_separately(monkeypatch):
    from api import health

    class Application:
        async def stats(self):
            return {
                "publish_queue_residence_seconds_p99": 2.0,
                "publish_delivery_duration_seconds_p99": 3.0,
                "publish_duration_seconds_p99": 5.0,
                "publish_credit_wait_seconds_p99": 1.5,
                "publish_encode_queue_wait_seconds_p99": 0.3,
                "publish_prepare_duration_seconds_p99": 0.1,
            }

    monkeypatch.setattr(health, "get_collection_application", lambda: Application())
    response = await health.prometheus_metrics(None)
    assert response.status == 200
    body = response.body.decode()
    assert "stargazer_collection_publish_queue_residence_seconds_p99 2.0" in body
    assert "stargazer_collection_publish_delivery_duration_seconds_p99 3.0" in body
    assert "stargazer_collection_publish_duration_seconds_p99 5.0" in body
    assert "stargazer_collection_publish_credit_wait_seconds_p99 1.5" in body
    assert "stargazer_collection_publish_encode_queue_wait_seconds_p99 0.3" in body
    assert "stargazer_collection_publish_prepare_duration_seconds_p99 0.1" in body


@pytest.mark.asyncio
async def test_deadline_preserves_the_phase_in_which_it_expired():
    jetstream = GatedJetStream()
    window = JetStreamPublishWindow(lambda: jetstream)
    try:
        with pytest.raises(JetStreamWindowPublishError) as caught:
            await window.publish("large", [JetStreamMessage(b"x", "deadline", asyncio.get_running_loop().time() + 0.03)])
        assert caught.value.timeout_stage == "deadline"
        assert caught.value.timeout_phase == "puback"
        assert window.snapshot().pending_messages == 0
    finally:
        jetstream.release.set()


@pytest.mark.asyncio
async def test_expired_credit_wait_never_marks_delivery_started():
    jetstream = GatedJetStream()
    window = JetStreamPublishWindow(lambda: jetstream, settings=JetStreamPublishWindowSettings(max_pending_messages=1))
    first = asyncio.create_task(window.publish("large", [JetStreamMessage(b"x", "first")]))
    await jetstream.first_chunk.wait()
    attempts = []
    try:
        with pytest.raises(JetStreamWindowPublishError):
            await window.publish(
                "large",
                [JetStreamMessage(b"x", "second", asyncio.get_running_loop().time() + 0.02)],
                before_publish=lambda index: attempts.append(index) or True,
            )
        assert attempts == []
    finally:
        jetstream.release.set()
        await first


@pytest.mark.asyncio
async def test_credit_is_released_when_admission_callback_cancels_or_raises():
    jetstream = GatedJetStream()
    window = JetStreamPublishWindow(lambda: jetstream)
    message = JetStreamMessage(b"x", "admission")
    assert await window.publish("large", [message], before_publish=lambda _: False) == 0
    assert window.snapshot().pending_messages == window.snapshot().pending_bytes == 0
    error = ValueError("admission failed")

    def fail(_index):
        raise error

    with pytest.raises(ValueError) as caught:
        await window.publish("large", [message], before_publish=fail)
    assert caught.value is error
    assert jetstream.large_lines == 0
    assert window.snapshot().pending_messages == window.snapshot().pending_bytes == 0


@pytest.mark.asyncio
async def test_deadline_expiring_behind_per_call_window_does_not_send_next_message():
    jetstream = GatedJetStream()
    window = JetStreamPublishWindow(lambda: jetstream, settings=JetStreamPublishWindowSettings(max_pending_messages_per_call=1))
    messages = [JetStreamMessage(b"x", "first"), JetStreamMessage(b"y", "expired", asyncio.get_running_loop().time() + 0.02)]
    publish = asyncio.create_task(window.publish("large", messages))
    await jetstream.first_chunk.wait()
    await asyncio.sleep(0.03)
    jetstream.release.set()
    with pytest.raises(JetStreamWindowPublishError) as caught:
        await publish
    assert caught.value.timeout_phase == "credit_wait"
    assert caught.value.attempted_indices == caught.value.confirmed_indices == (0,)
    assert jetstream.large_lines == 1
    assert window.snapshot().pending_messages == window.snapshot().pending_bytes == 0


@pytest.mark.asyncio
async def test_partial_confirmation_then_deadline_is_unknown_without_late_future_warning(monkeypatch):
    class PartialJetStream:
        count = 0

        async def publish_async(self, *args, **kwargs):
            self.count += 1
            future = asyncio.get_running_loop().create_future()
            if self.count <= 64:
                future.set_result(None)
            return future

    jetstream = PartialJetStream()
    window = JetStreamPublishWindow(lambda: jetstream, settings=JetStreamPublishWindowSettings(max_pending_messages_per_call=64))
    monkeypatch.setattr(nats_utils, "_metrics_js_window", window)
    publisher = BufferedResultPublisher(NatsResultPublisher(), capacity=1)
    request, lease = _request_and_lease(task_id="partial", plugin_ref="network", targets=("a",))
    coordinator = ResultDeliveryCoordinator(
        publisher=publisher,
        settings=TargetExecutorSettings(publish_total_timeout_seconds=0.2),
        metrics=CollectionMetrics(),
        request=request,
        lease=lease,
        log_identity="partial",
        failure_log_limit=0,
    )
    pending = await coordinator.enqueue(0, next(network_results(devices=1, lines_per_device=128)))
    try:
        terminal = await coordinator.finish(replace(pending, result=None))
        assert terminal[1] == "unknown"
    finally:
        await publisher.shutdown(grace_seconds=1)
    assert window.snapshot().confirmed_total == 64
    assert publisher.pending_payloads == window.snapshot().pending_messages == 0
    # 保留回执后再次读取，仍获得原始逐目标异常，而不是确认或重试。
    with pytest.raises(Exception) as caught:
        await pending.receipt.wait()
    assert caught.value.delivery_detected is True


@pytest.mark.asyncio
async def test_log_shaped_load_with_120_targets_in_flight():
    from scripts.benchmark_publish_fairness import parser, run_scenario

    report = await run_scenario(parser().parse_args(["--ack-ms", "1"]))
    assert report["terminal_counts"] == {"succeeded": 3838}
    assert report["confirmed_lines"] == 20214
    assert report["peak_payloads"] == report["peak_active_targets"] == 120
    assert report["peak_pending_messages"] <= 256
    assert report["remaining_payloads"] == report["remaining_messages"] == report["remaining_bytes"] == report["remaining_sdk_futures"] == 0


@pytest.mark.asyncio
async def test_shutdown_keeps_payload_owned_until_encoder_thread_releases_it(monkeypatch):
    entered = threading.Event()
    release = threading.Event()

    class SlowRows(dict):
        def items(self):
            entered.set()
            release.wait(3)
            return super().items()

    jetstream = GatedJetStream()
    monkeypatch.setattr(nats_utils, "_metrics_js_window", JetStreamPublishWindow(lambda: jetstream))
    publisher = BufferedResultPublisher(NatsResultPublisher(), capacity=1)
    request, lease = _request_and_lease(task_id="slow-encode", plugin_ref="network", targets=("a",))
    receipt = await publisher.enqueue(
        request,
        TargetCollectionResult(target="a", status="success", attempts=1, value=StructuredMetricsPayload(data=SlowRows(network=[{"ip": "a"}]))),
        lease,
    )
    async with asyncio.timeout(2):
        while not entered.is_set():
            await asyncio.sleep(0.001)
    shutdown = asyncio.create_task(publisher.shutdown(grace_seconds=0.001))
    try:
        await asyncio.sleep(0.03)
        assert publisher.pending_payloads == 1
        assert not shutdown.done()
    finally:
        release.set()
        jetstream.release.set()
        await shutdown
        await asyncio.gather(receipt.wait(), return_exceptions=True)
    assert publisher.pending_payloads == 0


@pytest.mark.asyncio
async def test_120_concurrent_deadlines_and_partial_acks_leave_no_resources():
    from scripts.benchmark_publish_fairness import parser, run_scenario

    report = await run_scenario(parser().parse_args(["--targets", "240", "--deadline", "0.15", "--ack-ms", "10", "--fail-every", "19"]))
    assert sum(report["terminal_counts"].values()) == 240
    assert report["terminal_counts"].get("unknown", 0) + report["terminal_counts"].get("failed", 0) > 0
    assert not any(key.startswith("exception:") for key in report["terminal_counts"])
    assert report["peak_payloads"] <= 120
    assert report["remaining_payloads"] == report["remaining_messages"] == report["remaining_bytes"] == report["remaining_sdk_futures"] == 0


@pytest.mark.asyncio
async def test_benchmark_uses_real_run_pipeline_and_recovers_exhausted_credit():
    from scripts.benchmark_publish_fairness import parser, run_scenario

    args = parser().parse_args(
        ["--pipeline", "run", "--targets", "240", "--large-lines", "128", "--credit-pause-seconds", "0.3", "--deadline", "0.2"]
    )
    report = await run_scenario(args)
    assert report["pipeline"] == "Scheduler/Executor/RunResultSink/Publisher"
    assert report["terminal_counts"] == {"succeeded": 240}
    assert report["collection_succeeded"] == 240
    assert report["peak_active_targets"] == report["peak_payloads"] == 120
    assert report["first_send_wait_p99_seconds"] > 0.2
    assert report["confirmed_lines"] == report["expected_lines"]
    assert report["remaining_tasks"] == report["remaining_payloads"] == report["remaining_messages"] == report["remaining_bytes"] == 0


@pytest.mark.asyncio
async def test_seven_real_runs_share_120_scheduler_slots_and_finish_3838_targets(monkeypatch):
    from core.collection.contracts import CollectOutcome, CollectOutcomeStatus, PreflightResult, PreflightStatus
    from core.collection.executor import TargetCollectionExecutor
    from core.collection.scheduler import CollectionScheduler

    from scripts.benchmark_publish_fairness import DelayedJetStream

    first_wave = asyncio.Event()
    collected = 0

    class Preflight:
        async def check(self, *args, **kwargs):
            return PreflightResult(status=PreflightStatus.REACHABLE)

    class Plugin:
        async def collect(self, target, credential, context):
            nonlocal collected
            collected += 1
            if collected >= 120:
                first_wave.set()
            await first_wave.wait()
            return CollectOutcome(status=CollectOutcomeStatus.SUCCESS, value=StructuredMetricsPayload(data={"network": [{"ip": target}]}))

    monkeypatch.setenv("NATS_JS_PUBLISH_MAX_PENDING", "256")
    monkeypatch.setenv("NATS_JS_PUBLISH_MAX_PENDING_PER_CALL", "64")
    jetstream = DelayedJetStream(0.001)
    window = JetStreamPublishWindow(lambda: jetstream, settings=JetStreamPublishWindowSettings(max_pending_messages_per_call=64))
    monkeypatch.setattr(nats_utils, "_metrics_js_window", window)
    publisher = BufferedResultPublisher(NatsResultPublisher(), capacity=120, worker_count=4)
    scheduler = CollectionScheduler(max_in_flight=120)
    executor = TargetCollectionExecutor(
        preflight=Preflight(),
        plugin=Plugin(),
        publisher=publisher,
        scheduler=scheduler,
        settings=TargetExecutorSettings(max_active_targets=120, target_task_window=120),
    )
    runs = []
    before = set(asyncio.all_tasks())
    try:
        for run in range(7):
            request, lease = _request_and_lease(
                task_id=f"real-run-{run}", plugin_ref="network", targets=tuple(f"target-{i}" for i in range(run, 3838, 7))
            )
            runs.append(executor.execute(request, lease))
        summaries = await asyncio.wait_for(asyncio.gather(*runs), 30)
        assert sum(summary.total for summary in summaries) == 3838
        assert sum(summary.collection_succeeded for summary in summaries) == 3838
        assert sum(summary.publish_succeeded for summary in summaries) == 3838
        assert scheduler.peak == publisher.peak_pending_payloads == 120
    finally:
        await scheduler.shutdown()
        await publisher.shutdown()
    assert publisher.pending_payloads == window.snapshot().pending_messages == 0
    assert not [task for task in asyncio.all_tasks() - before if not task.done()]
