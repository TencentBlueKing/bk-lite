import asyncio
import gc
import time
import weakref

import pytest
from core.collection.contracts import StructuredMetricsPayload, TargetCollectionResult
from core.collection.metrics import CollectionMetrics
from core.collection.result_delivery import PendingPublish
from core.collection.run_result_sink import RunResultSink


class ImmediateDelivery:
    async def finish(self, pending):
        return pending.index, "succeeded", ""


class BlockingDelivery:
    def __init__(self):
        self.release = asyncio.Event()
        self.started = 0

    async def finish(self, pending):
        self.started += 1
        await self.release.wait()
        return pending.index, "succeeded", ""


def _pending(index, result, *, delivery_required=True):
    return PendingPublish(
        index=index,
        result=result,
        receipt=object() if delivery_required else None,
        started_at=time.monotonic(),
        deadline=time.monotonic() + 10,
        delivery_required=delivery_required,
    )


@pytest.mark.asyncio
async def test_success_payload_is_released_after_delivery_terminal_state():
    payload = StructuredMetricsPayload(data={"network": [{"blob": "x" * 1024}]})
    payload_reference = weakref.ref(payload)
    result = TargetCollectionResult(
        target="10.0.0.1",
        status="success",
        attempts=1,
        value=payload,
    )
    pending = _pending(0, result)
    sink = RunResultSink(
        delivery=ImmediateDelivery(),
        metrics=CollectionMetrics(),
        total_targets=1,
    )

    await sink.accept(pending)
    del pending, result, payload
    report = await sink.finish()
    await asyncio.sleep(0)
    gc.collect()

    assert report.summary.collection_succeeded == 1
    assert report.summary.publish_succeeded == 1
    assert sink.pending_deliveries == 0
    assert payload_reference() is None


@pytest.mark.asyncio
async def test_failures_keep_only_bounded_counts_and_three_samples():
    sink = RunResultSink(
        delivery=ImmediateDelivery(),
        metrics=CollectionMetrics(),
        total_targets=5000,
    )

    for index in range(5000):
        result = TargetCollectionResult(
            target=f"target-{index}",
            status="unreachable",
            attempts=1,
            error_code="snmp_no_response",
        )
        await sink.accept(_pending(index, result, delivery_required=False))

    report = await sink.finish()

    assert report.summary.unreachable == 5000
    assert report.summary.publish_not_applicable == 5000
    assert report.failure_codes == "snmp_no_response:5000"
    assert report.failure_sample_count == 3
    assert report.total_failures == 5000
    assert report.failure_samples.count("|snmp_no_response") == 3


@pytest.mark.asyncio
async def test_finish_waits_for_all_delivery_terminal_states_without_storing_completed_payloads():
    delivery = BlockingDelivery()
    metrics = CollectionMetrics()
    sink = RunResultSink(
        delivery=delivery,
        metrics=metrics,
        total_targets=160,
    )
    for index in range(160):
        await sink.accept(
            _pending(
                index,
                TargetCollectionResult(
                    target=f"target-{index}",
                    status="success",
                    attempts=1,
                    value={"index": index},
                ),
            )
        )

    await asyncio.sleep(0)
    finishing = asyncio.create_task(sink.finish())
    await asyncio.sleep(0)

    assert 0 < delivery.started < 160
    assert sink.pending_deliveries == 160
    assert metrics.snapshot()["result_deliveries_pending"] == 160
    assert finishing.done() is False

    delivery.release.set()
    report = await finishing

    assert sink.pending_deliveries == 0
    assert metrics.snapshot()["result_deliveries_pending"] == 0
    assert report.summary.total == 160
    assert report.summary.publish_succeeded == 160


@pytest.mark.asyncio
async def test_abort_cancels_fixed_delivery_workers_and_releases_payloads():
    delivery = BlockingDelivery()
    sink = RunResultSink(
        delivery=delivery,
        metrics=CollectionMetrics(),
        total_targets=1,
    )
    payload = StructuredMetricsPayload(data={"network": [{"blob": "x" * 1024}]})
    payload_reference = weakref.ref(payload)
    pending = _pending(
        0,
        TargetCollectionResult(
            target="target-0",
            status="success",
            attempts=1,
            value=payload,
        ),
    )

    await sink.accept(pending)
    await asyncio.sleep(0)
    del pending, payload
    await asyncio.wait_for(sink.abort(), timeout=1)
    await asyncio.sleep(0)
    gc.collect()

    assert payload_reference() is None
    assert sink.pending_deliveries == 0


@pytest.mark.asyncio
async def test_transport_managed_receipt_is_observed_without_retaining_the_payload():
    class TransportManagedReceipt:
        retries_managed = True

    delivery = BlockingDelivery()
    sink = RunResultSink(
        delivery=delivery,
        metrics=CollectionMetrics(),
        total_targets=1,
    )
    payload = StructuredMetricsPayload(data={"network": [{"blob": "x" * 1024}]})
    payload_reference = weakref.ref(payload)
    result = TargetCollectionResult(
        target="target-0",
        status="success",
        attempts=1,
        value=payload,
    )
    pending = PendingPublish(
        index=0,
        result=result,
        receipt=TransportManagedReceipt(),
        started_at=time.monotonic(),
        deadline=time.monotonic() + 10,
    )

    await sink.accept(pending)
    del pending, result, payload
    gc.collect()

    assert payload_reference() is None

    delivery.release.set()
    await sink.finish()
