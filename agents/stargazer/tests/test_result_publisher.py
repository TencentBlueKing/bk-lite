import asyncio

import pytest
from core.collection.contracts import CredentialFailureResult, TargetCollectionResult, build_collection_result_id
from core.collection.result_publisher import BufferedResultPublisher, NatsResultPublisher, PublishShutdownError
from core.collection.runtime import CollectionRequest, RunLease


@pytest.mark.asyncio
async def test_buffered_publisher_batches_concurrent_target_results():
    batches = []

    class BatchDelegate:
        async def publish_batch(self, items):
            batches.append(tuple(item[1].target for item in items))

    publisher = BufferedResultPublisher(BatchDelegate(), capacity=3, batch_size=10, flush_interval_seconds=0.01)
    request = CollectionRequest(
        task_id="batch-results",
        plugin_ref="network.config",
        targets=("10.10.24.1", "10.10.24.2", "10.10.24.3"),
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999)

    await asyncio.gather(
        *(
            publisher.publish(
                request,
                TargetCollectionResult(target=target, status="success", attempts=1, value="metric 1"),
                lease,
            )
            for target in request.targets
        )
    )

    assert batches == [("10.10.24.1", "10.10.24.2", "10.10.24.3")]
    assert publisher.peak_queue_depth <= 3
    await publisher.shutdown()


@pytest.mark.asyncio
async def test_enqueue_returns_receipt_before_slow_delivery_finishes():
    release = asyncio.Event()

    class SlowDelegate:
        async def publish_batch(self, items):
            await release.wait()

    publisher = BufferedResultPublisher(SlowDelegate(), capacity=1, batch_size=1, flush_interval_seconds=0.01)
    request = CollectionRequest(
        task_id="publish-receipt",
        plugin_ref="network.config",
        targets=("10.10.24.1",),
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999)

    receipt = await publisher.enqueue(
        request,
        TargetCollectionResult(target="10.10.24.1", status="success", attempts=1, value="metric 1"),
        lease,
    )

    assert receipt.done() is False
    release.set()
    await receipt.wait()
    assert receipt.done() is True
    await publisher.shutdown()


@pytest.mark.asyncio
async def test_shutdown_grace_cancels_hung_writer_and_resolves_receipt():
    blocked = asyncio.Event()

    class HungDelegate:
        async def publish_batch(self, _items):
            await blocked.wait()

    publisher = BufferedResultPublisher(HungDelegate(), capacity=1, batch_size=1, flush_interval_seconds=0.01)
    request = CollectionRequest(
        task_id="publisher-shutdown-grace",
        plugin_ref="network.config",
        targets=("10.10.24.1",),
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999)
    receipt = await publisher.enqueue(
        request,
        TargetCollectionResult(target="10.10.24.1", status="success", attempts=1, value="metric 1"),
        lease,
    )

    await publisher.shutdown(grace_seconds=0.01)
    outcome = await asyncio.gather(receipt.wait(), return_exceptions=True)

    assert isinstance(outcome[0], PublishShutdownError)
    assert receipt.done() is True


@pytest.mark.asyncio
async def test_batch_delegate_can_report_one_failed_result_without_poisoning_peers():
    request = CollectionRequest(
        task_id="batch-partial-result",
        plugin_ref="network.config",
        targets=("10.10.24.1", "10.10.24.2", "10.10.24.3"),
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 7, 999999)
    failed_id = build_collection_result_id(
        task_id=request.task_id,
        plugin_ref=request.plugin_ref,
        target="10.10.24.2",
        fence=lease.fence,
    )

    class PartialDelegate:
        async def publish_batch(self, items):
            return {failed_id: TimeoutError("target publish failed")}

    publisher = BufferedResultPublisher(PartialDelegate(), capacity=3, batch_size=3, flush_interval_seconds=0.01)
    receipts = await asyncio.gather(
        *(
            publisher.enqueue(
                request,
                TargetCollectionResult(target=target, status="success", attempts=1, value="metric 1"),
                lease,
            )
            for target in request.targets
        )
    )
    outcomes = await asyncio.gather(*(receipt.wait() for receipt in receipts), return_exceptions=True)

    assert outcomes[0] is None
    assert isinstance(outcomes[1], TimeoutError)
    assert outcomes[2] is None
    await publisher.shutdown()


@pytest.mark.asyncio
async def test_nats_result_publisher_uses_one_metrics_batch_adapter_call():
    batches = []

    async def publish_metrics_batch(entries):
        batches.append(entries)

    publisher = NatsResultPublisher(metrics_publish_batch=publish_metrics_batch)
    request = CollectionRequest(
        task_id="nats-batch",
        plugin_ref="network.config",
        targets=("10.10.24.1", "10.10.24.2"),
        params={"plugin_family": "configuration", "model_id": "network"},
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999)

    await publisher.publish_batch(
        tuple(
            (
                request,
                TargetCollectionResult(
                    target=target,
                    status="success",
                    attempts=1,
                    value=f"network_info,host={target} value=1",
                ),
                lease,
            )
            for target in request.targets
        )
    )

    assert len(batches) == 1
    assert [entry[3] for entry in batches[0]] == ["nats-batch", "nats-batch"]
    assert all("collection_result_id" in entry[2] for entry in batches[0])


@pytest.mark.asyncio
async def test_nats_batch_returns_per_target_adapter_outcomes():
    request = CollectionRequest(
        task_id="nats-partial-batch",
        plugin_ref="network.config",
        targets=("10.10.24.1", "10.10.24.2"),
        params={"plugin_family": "configuration", "model_id": "network"},
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 3, 999999)
    failed_id = build_collection_result_id(
        task_id=request.task_id,
        plugin_ref=request.plugin_ref,
        target="10.10.24.2",
        fence=lease.fence,
    )

    async def publish_metrics_batch(entries):
        assert len(entries) == 2
        return {failed_id: TimeoutError("second target failed")}

    publisher = NatsResultPublisher(metrics_publish_batch=publish_metrics_batch)
    outcomes = await publisher.publish_batch(
        tuple(
            (
                request,
                TargetCollectionResult(
                    target=target,
                    status="success",
                    attempts=1,
                    value=f"network_info,host={target} value=1",
                ),
                lease,
            )
            for target in request.targets
        )
    )

    succeeded_id = build_collection_result_id(
        task_id=request.task_id,
        plugin_ref=request.plugin_ref,
        target="10.10.24.1",
        fence=lease.fence,
    )
    assert outcomes[succeeded_id] is None
    assert isinstance(outcomes[failed_id], TimeoutError)


@pytest.mark.asyncio
async def test_credential_result_event_declares_v2_contract():
    events = []

    async def record_event(event):
        events.append(event)

    publisher = NatsResultPublisher(result_event_sink=record_event)
    request = CollectionRequest(
        task_id="collect-result-event",
        plugin_ref="mysql.config",
        targets=("10.10.24.1",),
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="pod-a",
        fence=7,
        expires_at=999999,
        attempt_id="run-attempt-1",
    )

    await publisher._record_event(
        request,
        TargetCollectionResult(
            target="10.10.24.1",
            status="success",
            attempts=1,
            credential_id="credential-1",
        ),
        lease,
        "result-id",
    )

    assert len(events[0].pop("event_id")) == 64
    assert events == [
        {
            "event_version": 2,
            "producer": "stargazer",
            "scope_id": "collect-result-event",
            "collect_task_id": "collect-result-event",
            "run_id": "collect-result-event",
            "run_attempt_id": "run-attempt-1",
            "producer_instance": "pod-a",
            "plugin_ref": "mysql.config",
            "host": "10.10.24.1",
            "credential_id": "credential-1",
            "status": "success",
            "error_code": "",
            "success": True,
            "failure_kind": "",
            "error_message": "",
            "attempts": 1,
            "fence": 7,
            "result_id": "result-id",
            "event_index": 0,
        }
    ]


@pytest.mark.asyncio
async def test_credential_result_event_expands_rotated_credential_failures():
    events = []

    async def record_event(event):
        events.append(event)

    publisher = NatsResultPublisher(result_event_sink=record_event)
    request = CollectionRequest(
        task_id="collect-result-rotation",
        plugin_ref="mysql.config",
        targets=("10.10.24.1",),
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="pod-a",
        fence=7,
        expires_at=999999,
        attempt_id="run-attempt-1",
    )

    await publisher._record_event(
        request,
        TargetCollectionResult(
            target="10.10.24.1",
            status="success",
            attempts=3,
            credential_id="credential-3",
            credential_failures=(
                CredentialFailureResult("credential-1", "unauthorized"),
                CredentialFailureResult("credential-2", "authentication_failed"),
            ),
        ),
        lease,
        "result-id",
    )

    assert [event["credential_id"] for event in events] == [
        "credential-1",
        "credential-2",
        "credential-3",
    ]
    assert [(event["status"], event["success"]) for event in events] == [
        ("failed", False),
        ("failed", False),
        ("success", True),
    ]
    assert [event["failure_kind"] for event in events] == [
        "credential",
        "credential",
        "",
    ]
    assert all(event["event_version"] == 2 for event in events)


@pytest.mark.asyncio
async def test_credential_result_event_ids_are_stable_across_partial_retry():
    attempts = []
    fail_second_once = True

    async def partially_failing_sink(event):
        nonlocal fail_second_once
        attempts.append(event)
        if fail_second_once and len(attempts) == 2:
            fail_second_once = False
            raise ConnectionError("partial write")

    publisher = NatsResultPublisher(result_event_sink=partially_failing_sink)
    request = CollectionRequest(
        task_id="collect-result-partial-retry",
        plugin_ref="mysql.config",
        targets=("10.10.24.1",),
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="pod-a",
        fence=7,
        expires_at=999999,
        attempt_id="run-attempt-1",
    )
    result = TargetCollectionResult(
        target="10.10.24.1",
        status="success",
        attempts=3,
        credential_id="credential-3",
        credential_failures=(
            CredentialFailureResult("credential-1", "unauthorized"),
            CredentialFailureResult("credential-2", "authentication_failed"),
        ),
    )

    with pytest.raises(ConnectionError, match="partial write"):
        await publisher._record_event(request, result, lease, "result-id")
    await publisher._record_event(request, result, lease, "result-id")

    first_attempt_id = attempts[0]["event_id"]
    retried_first_id = attempts[2]["event_id"]
    assert first_attempt_id == retried_first_id
    assert len({event["event_id"] for event in attempts[2:]}) == 3


@pytest.mark.asyncio
async def test_credential_result_event_omits_empty_aggregate_after_failures():
    events = []

    async def record_event(event):
        events.append(event)

    publisher = NatsResultPublisher(result_event_sink=record_event)
    request = CollectionRequest(
        task_id="collect-result-exhausted",
        plugin_ref="mysql.config",
        targets=("10.10.24.1",),
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="pod-a",
        fence=7,
        expires_at=999999,
        attempt_id="run-attempt-1",
    )

    await publisher._record_event(
        request,
        TargetCollectionResult(
            target="10.10.24.1",
            status="failed",
            attempts=1,
            error_code="credentials_exhausted",
            credential_failures=(CredentialFailureResult("credential-1", "capability_denied"),),
        ),
        lease,
        "result-id",
    )

    assert len(events) == 1
    assert events[0]["credential_id"] == "credential-1"
    assert events[0]["error_code"] == "capability_denied"
    assert events[0]["failure_kind"] == "credential"


@pytest.mark.asyncio
async def test_metrics_result_carries_idempotency_and_fencing_identity():
    published = []

    async def publish_metrics(ctx, value, params, task_id):
        published.append((ctx, value, params, task_id))
        return 1

    publisher = NatsResultPublisher(metrics_publish=publish_metrics)
    request = CollectionRequest(
        task_id="collect-result",
        plugin_ref="mysql.config",
        targets=("10.10.24.1",),
        params={"plugin_family": "configuration", "model_id": "mysql"},
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="pod-a",
        fence=7,
        expires_at=999999,
        attempt_id="run-attempt-1",
    )

    await publisher.publish(
        request,
        TargetCollectionResult(
            target="10.10.24.1",
            status="success",
            attempts=1,
            credential_id="credential-1",
            value="mysql_info 1",
        ),
        lease,
    )

    params = published[0][2]
    assert params["collection_task_id"] == "collect-result"
    assert params["collection_fence"] == 7
    assert params["collection_target"] == "10.10.24.1"
    assert params["collection_plugin_ref"] == "mysql.config"
    assert len(params["collection_result_id"]) == 64
    assert "credential-1" not in str(params)


@pytest.mark.asyncio
async def test_callback_result_includes_fence_and_is_not_sent_as_metrics():
    callbacks = []

    async def publish_callback(value, params, task_id):
        callbacks.append((value, params, task_id))

    async def unexpected_metrics(*args):
        raise AssertionError("callback result must not use metrics publisher")

    publisher = NatsResultPublisher(
        metrics_publish=unexpected_metrics,
        callback_publish=publish_callback,
    )
    request = CollectionRequest(
        task_id="callback-result",
        plugin_ref="config_file.config",
        targets=("10.10.24.2",),
        params={"callback_subject": "receive_config_file_result"},
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="pod-a",
        fence=4,
        expires_at=999999,
        attempt_id="run-attempt-1",
    )

    await publisher.publish(
        request,
        TargetCollectionResult(
            target="10.10.24.2",
            status="success",
            attempts=1,
            value={"status": "success"},
        ),
        lease,
    )

    assert callbacks[0][0]["collection_fence"] == 4
    assert callbacks[0][0]["collection_target"] == "10.10.24.2"
