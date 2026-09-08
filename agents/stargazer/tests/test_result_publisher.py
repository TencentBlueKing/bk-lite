import asyncio
from types import SimpleNamespace

import core.infra.nats_utils as nats_utils
import pytest
from core.collection.contracts import PublishStatus, StructuredMetricsPayload, TargetCollectionResult, build_collection_result_id
from core.collection.result_delivery import _requires_delivery
from core.collection.result_publisher import BufferedResultPublisher, NatsResultPublisher, PublishShutdownError
from core.collection.runtime import CollectionRequest, RunLease


@pytest.mark.asyncio
async def test_expired_deadline_stops_before_round_metadata_and_metrics_delivery():
    events = []

    class Store:
        async def save(self, _envelope):
            events.append("metadata")

    async def publish_metrics_batch(_entries):
        events.append("metrics")
        return {}

    request = CollectionRequest(
        task_id="expired-before-publish",
        plugin_ref="network.config",
        targets=("10.0.0.8",),
        params={"model_id": "network", "plugin_family": "configuration"},
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999, attempt_id="attempt-a")
    result = TargetCollectionResult(
        target="10.0.0.8",
        status="success",
        attempts=1,
        value=StructuredMetricsPayload(
            data={"network": [{"host": "10.0.0.8"}]},
            round_metadata={
                "snapshot_id": "snapshot-1",
                "snapshot_status": "complete",
                "details": {},
            },
        ),
    )

    outcomes = await NatsResultPublisher(
        metrics_publish_batch=publish_metrics_batch,
        round_metadata_store=Store(),
    ).publish_batch(((request, result, lease, SimpleNamespace(deadline=0.0)),))

    assert events == []
    assert list(outcomes.values())[0].status == PublishStatus.RETRYABLE_FAILED
    assert list(outcomes.values())[0].error_code == "publish_total_timeout_before_delivery"


@pytest.mark.asyncio
async def test_snapshot_metadata_is_persisted_before_metric_delivery():
    events = []

    class Store:
        async def save(self, envelope):
            events.append(("metadata", envelope))
            return "created"

    async def publish_metrics_batch(_entries):
        events.append(("metrics", None))
        return {}

    request = CollectionRequest(
        task_id="321",
        plugin_ref="pc.config",
        targets=("10.0.0.8",),
        params={"model_id": "pc", "plugin_family": "configuration"},
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999, attempt_id="attempt-a")
    result = TargetCollectionResult(
        target="10.0.0.8",
        status="success",
        attempts=1,
        publish_timestamp_ms=1780000000123,
        value=StructuredMetricsPayload(
            data={"pc": [{"inst_name": "WIN-AAA"}]},
            round_metadata={
                "snapshot_id": "snapshot-1",
                "snapshot_status": "complete",
                "details": {"software_expected_count": 0, "software_error_count": 0},
            },
        ),
    )

    outcomes = await NatsResultPublisher(
        metrics_publish_batch=publish_metrics_batch,
        round_metadata_store=Store(),
    ).publish_batch(((request, result, lease),))

    assert [event[0] for event in events] == ["metadata", "metrics"]
    metadata = events[0][1]
    assert metadata["collection_task_id"] == "321"
    assert metadata["collection_target"] == "10.0.0.8"
    assert metadata["publish_timestamp_ms"] == 1780000000123
    assert list(outcomes.values()) == [None]


@pytest.mark.asyncio
async def test_snapshot_metadata_failure_prevents_metric_delivery():
    published = False

    class Store:
        async def save(self, _envelope):
            raise ConnectionError("redis unavailable")

    async def publish_metrics_batch(_entries):
        nonlocal published
        published = True
        return {}

    request = CollectionRequest(
        task_id="321",
        plugin_ref="winsphere.config",
        targets=("10.0.0.10",),
        params={"model_id": "winsphere", "plugin_family": "configuration"},
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999, attempt_id="attempt-a")
    result = TargetCollectionResult(
        target="10.0.0.10",
        status="success",
        attempts=1,
        publish_timestamp_ms=1780000000123,
        value=StructuredMetricsPayload(
            data={"winsphere": [{"resource_id": "platform-1"}]},
            round_metadata={
                "snapshot_id": "snapshot-1",
                "snapshot_status": "complete",
                "details": {"snapshot_manifest": {}},
            },
        ),
    )

    outcomes = await NatsResultPublisher(
        metrics_publish_batch=publish_metrics_batch,
        round_metadata_store=Store(),
    ).publish_batch(((request, result, lease),))

    assert published is False
    assert isinstance(next(iter(outcomes.values())), ConnectionError)


@pytest.mark.asyncio
async def test_snapshot_models_without_round_metadata_are_rejected_before_metric_delivery():
    published = False

    async def publish_metrics_batch(_entries):
        nonlocal published
        published = True
        return {}

    request = CollectionRequest(
        task_id="321",
        plugin_ref="pc.config",
        targets=("10.0.0.8",),
        params={"model_id": "pc", "plugin_family": "configuration"},
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999, attempt_id="attempt-a")
    result = TargetCollectionResult(
        target="10.0.0.8",
        status="success",
        attempts=1,
        publish_timestamp_ms=1780000000123,
        value=StructuredMetricsPayload(data={"pc": [{"inst_name": "WIN-AAA"}]}),
    )

    outcomes = await NatsResultPublisher(
        metrics_publish_batch=publish_metrics_batch,
        round_metadata_store=object(),
    ).publish_batch(((request, result, lease),))

    outcome = next(iter(outcomes.values()))
    assert published is False
    assert outcome.status == PublishStatus.PERMANENT_FAILED
    assert outcome.error_code == "metadata_missing"


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
async def test_publish_receipt_exposes_queue_and_delivery_telemetry():
    delivery_started = asyncio.Event()
    release = asyncio.Event()

    class ObservableDelegate:
        tracks_transport_attempts = True

        async def publish_batch(self, items):
            assert items[0][3].mark_delivery_started() is True
            delivery_started.set()
            await release.wait()

    publisher = BufferedResultPublisher(ObservableDelegate(), capacity=2, batch_size=1, flush_interval_seconds=0.01)
    request = CollectionRequest(
        task_id="publish-telemetry",
        plugin_ref="network.config",
        targets=("10.10.24.1",),
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999)

    receipt = await publisher.enqueue(
        request,
        TargetCollectionResult(target="10.10.24.1", status="success", attempts=1, value="metric 1"),
        lease,
    )
    await delivery_started.wait()

    assert receipt.delivery_started is True
    assert receipt.queue_depth_at_enqueue == 1
    assert receipt.queue_wait_seconds >= 0
    assert receipt.queue_age_seconds >= 0
    assert receipt.queue_residence_seconds >= 0

    release.set()
    await receipt.wait()
    await publisher.shutdown()


@pytest.mark.asyncio
async def test_buffered_publisher_carries_the_result_deadline_to_the_transport_attempt():
    observed_deadline = None

    class DeadlineAwareDelegate:
        async def publish_batch(self, items):
            nonlocal observed_deadline
            observed_deadline = items[0][3].deadline

    publisher = BufferedResultPublisher(DeadlineAwareDelegate(), capacity=1, batch_size=1)
    request = CollectionRequest(
        task_id="publish-deadline",
        plugin_ref="network.config",
        targets=("10.10.24.1",),
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999)
    deadline = asyncio.get_running_loop().time() + 30

    receipt = await publisher.enqueue(
        request,
        TargetCollectionResult(target="10.10.24.1", status="success", attempts=1, value="metric 1"),
        lease,
        deadline=deadline,
    )

    await receipt.wait()
    assert observed_deadline == deadline
    await publisher.shutdown()


@pytest.mark.asyncio
async def test_payload_capacity_includes_results_already_taken_by_active_writers():
    two_started = asyncio.Event()
    release = asyncio.Event()
    started = []

    class BlockingDelegate:
        async def publish_batch(self, items):
            started.extend(item[1].target for item in items)
            if len(started) >= 2:
                two_started.set()
            await release.wait()

    publisher = BufferedResultPublisher(
        BlockingDelegate(),
        capacity=2,
        batch_size=1,
        worker_count=2,
    )
    request = CollectionRequest(
        task_id="payload-capacity",
        plugin_ref="network.config",
        targets=("10.10.24.1", "10.10.24.2", "10.10.24.3"),
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999)

    first, second = await asyncio.gather(
        *(
            publisher.enqueue(
                request,
                TargetCollectionResult(target=target, status="success", attempts=1, value="metric 1"),
                lease,
            )
            for target in request.targets[:2]
        )
    )
    await asyncio.wait_for(two_started.wait(), timeout=1)
    assert publisher.queue_depth == 0
    assert publisher.pending_payloads == 2

    third_enqueue = asyncio.create_task(
        publisher.enqueue(
            request,
            TargetCollectionResult(target="10.10.24.3", status="success", attempts=1, value="metric 1"),
            lease,
        )
    )
    await asyncio.sleep(0)

    assert third_enqueue.done() is False
    assert publisher.peak_pending_payloads == 2

    release.set()
    await asyncio.gather(first.wait(), second.wait())
    third = await asyncio.wait_for(third_enqueue, timeout=1)
    await third.wait()
    assert publisher.pending_payloads == 0
    await publisher.shutdown()


@pytest.mark.asyncio
async def test_queued_receipt_can_be_cancelled_before_transport_and_is_not_delivered_later():
    release = asyncio.Event()
    delivered = []

    class BlockingDelegate:
        async def publish_batch(self, items):
            delivered.extend(item[1].target for item in items)
            if "10.10.24.1" in delivered:
                await release.wait()

    publisher = BufferedResultPublisher(BlockingDelegate(), capacity=2, batch_size=1, flush_interval_seconds=0.01)
    request = CollectionRequest(
        task_id="cancel-before-delivery",
        plugin_ref="network.config",
        targets=("10.10.24.1", "10.10.24.2"),
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999, attempt_id="attempt-a")
    first = await publisher.enqueue(
        request,
        TargetCollectionResult(target="10.10.24.1", status="success", attempts=1, value="metric 1"),
        lease,
    )
    second = await publisher.enqueue(
        request,
        TargetCollectionResult(target="10.10.24.2", status="success", attempts=1, value="metric 1"),
        lease,
    )
    await asyncio.sleep(0)

    assert second.cancel_if_unattempted() is True
    outcome = await second.wait()
    assert outcome.status == PublishStatus.RETRYABLE_FAILED

    release.set()
    await first.wait()
    await publisher.shutdown()

    assert delivered == ["10.10.24.1"]


@pytest.mark.asyncio
async def test_receipt_cancelled_while_connecting_never_calls_nats_publish(monkeypatch):
    monkeypatch.setenv("NATS_METRICS_JETSTREAM_ENABLED", "false")
    monkeypatch.setenv("NATS_METRICS_CORE_FALLBACK_ENABLED", "true")
    connecting = asyncio.Event()
    release_connection = asyncio.Event()
    publish_calls = 0

    class FakeNats:
        async def publish(self, _subject, _payload):
            nonlocal publish_calls
            publish_calls += 1

        async def flush(self, timeout=None):
            return None

    async def get_nats(_channel="control"):
        connecting.set()
        await release_connection.wait()
        return FakeNats()

    monkeypatch.setattr(nats_utils, "get_shared_nats", get_nats)
    publisher = BufferedResultPublisher(NatsResultPublisher(), capacity=1, batch_size=1)
    request = CollectionRequest(
        task_id="cancel-while-connecting",
        plugin_ref="network.config",
        targets=("10.10.24.1",),
        params={"plugin_family": "configuration", "model_id": "network"},
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999, attempt_id="attempt-a")
    receipt = await publisher.enqueue(
        request,
        TargetCollectionResult(
            target="10.10.24.1",
            status="success",
            attempts=1,
            value="network_info value=1",
        ),
        lease,
    )
    await connecting.wait()

    assert receipt.cancel_if_unattempted() is True
    assert (await receipt.wait()).status == PublishStatus.RETRYABLE_FAILED
    release_connection.set()
    await publisher.shutdown()

    assert publish_calls == 0


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

    assert outcomes[0].status == PublishStatus.CONFIRMED
    assert isinstance(outcomes[1], TimeoutError)
    assert outcomes[2].status == PublishStatus.CONFIRMED
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
    assert all(entry[2]["collect_status"] == "success" for entry in batches[0])


@pytest.mark.asyncio
async def test_ordinary_failures_do_not_enter_metrics_or_credential_adapters():
    batches = []
    published_credentials = []

    async def publish_metrics_batch(entries):
        batches.append(entries)
        return {entry[2]["collection_result_id"]: None for entry in entries}

    async def publish_credential(result, params, task_id):
        published_credentials.append((result, params, task_id))

    publisher = NatsResultPublisher(
        metrics_publish_batch=publish_metrics_batch,
        credential_result_publish=publish_credential,
    )
    request = CollectionRequest(
        task_id="configuration-failure-event-only",
        plugin_ref="network.config",
        targets=("10.10.24.1", "10.10.24.2", "10.10.24.3"),
        params={
            "plugin_family": "configuration",
            "model_id": "network",
            "credential_result_subject": "receive_collect_credential_result",
        },
    )
    lease = RunLease(
        request.task_id,
        request.digest,
        "pod-a",
        1,
        999999,
        attempt_id="attempt-a",
    )

    outcomes = await publisher.publish_batch(
        (
            (
                request,
                TargetCollectionResult(
                    target="10.10.24.1",
                    status="success",
                    attempts=1,
                    credential_id="credential-1",
                    value="network_info value=1",
                ),
                lease,
            ),
            (
                request,
                TargetCollectionResult(
                    target="10.10.24.2",
                    status="failed",
                    attempts=1,
                    credential_id="credential-1",
                    error_code="authentication_failed",
                ),
                lease,
            ),
            (
                request,
                TargetCollectionResult(
                    target="10.10.24.3",
                    status="unreachable",
                    attempts=0,
                    error_code="target_unreachable",
                ),
                lease,
            ),
        )
    )

    assert len(batches) == 1
    assert len(batches[0]) == 1
    assert batches[0][0][1] == "network_info value=1"
    assert published_credentials == []
    assert not hasattr(publisher, "_result_event_sink")
    assert all(outcome is None for outcome in outcomes.values())


@pytest.mark.asyncio
async def test_empty_structured_success_does_not_enter_metrics_adapter():
    batches = []

    async def publish_metrics_batch(entries):
        batches.append(entries)
        return {}

    publisher = NatsResultPublisher(metrics_publish_batch=publish_metrics_batch)
    request = CollectionRequest(
        task_id="empty-success",
        plugin_ref="mysql.config",
        targets=("10.10.24.1",),
        params={"plugin_family": "configuration", "model_id": "mysql"},
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999)

    outcomes = await publisher.publish_batch(
        (
            (
                request,
                TargetCollectionResult(
                    target="10.10.24.1",
                    status="success",
                    attempts=1,
                    value=StructuredMetricsPayload(data={"mysql": ()}),
                ),
                lease,
            ),
        )
    )

    assert batches == []
    assert tuple(outcomes.values()) == (None,)


def test_legacy_result_event_adapter_is_not_part_of_publisher_interface():
    with pytest.raises(TypeError, match="result_event_sink"):
        NatsResultPublisher(result_event_sink=lambda _event: None)


@pytest.mark.asyncio
async def test_monitor_failure_does_not_generate_error_metrics():
    batches = []

    async def publish_metrics_batch(entries):
        batches.append(entries)
        return {entry[2]["collection_result_id"]: None for entry in entries}

    publisher = NatsResultPublisher(metrics_publish_batch=publish_metrics_batch)
    request = CollectionRequest(
        task_id="monitor-failure-metric",
        plugin_ref="host.monitor",
        targets=("10.10.24.1",),
        params={
            "plugin_family": "monitor",
            "monitor_type": "host",
            "model_id": "host",
        },
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999)

    await publisher.publish_batch(
        (
            (
                request,
                TargetCollectionResult(
                    target="10.10.24.1",
                    status="failed",
                    attempts=1,
                    error_code="monitor_failed",
                ),
                lease,
            ),
        )
    )

    assert batches == []


@pytest.mark.asyncio
async def test_batch_result_id_changes_between_attempts_with_same_task_target_and_fence():
    result_ids = []

    async def publish_metrics_batch(entries):
        result_ids.extend(entry[2]["collection_result_id"] for entry in entries)
        return {entry[2]["collection_result_id"]: None for entry in entries}

    publisher = NatsResultPublisher(metrics_publish_batch=publish_metrics_batch)
    request = CollectionRequest(
        task_id="periodic-network-task",
        plugin_ref="network.config",
        targets=("10.10.24.1",),
        params={"plugin_family": "configuration", "model_id": "network"},
    )
    result = TargetCollectionResult(target="10.10.24.1", status="success", attempts=1, value="network_info value=1")

    for attempt_id in ("attempt-a", "attempt-b"):
        lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999, attempt_id=attempt_id)
        await publisher.publish_batch(((request, result, lease),))

    assert len(result_ids) == 2
    assert result_ids[0] != result_ids[1]


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


@pytest.mark.asyncio
async def test_configuration_failure_with_callback_keeps_callback_contract():
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
        task_id="callback-failure-result",
        plugin_ref="config_file.config",
        targets=("10.10.24.2",),
        params={
            "plugin_family": "configuration",
            "callback_subject": "receive_config_file_result",
        },
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
            status="failed",
            attempts=1,
            error_code="config_file_failed",
            value={"status": "failed"},
        ),
        lease,
    )

    assert len(callbacks) == 1
    assert callbacks[0][0]["status"] == "failed"
    assert callbacks[0][0]["collection_fence"] == 4


@pytest.mark.asyncio
async def test_callback_transport_failure_is_reported_without_metrics_fallback():
    metrics_called = False

    async def failed_callback(*_args):
        raise ConnectionError("control nats unavailable")

    async def unexpected_metrics(*_args):
        nonlocal metrics_called
        metrics_called = True

    publisher = NatsResultPublisher(
        metrics_publish=unexpected_metrics,
        callback_publish=failed_callback,
    )
    request = CollectionRequest(
        task_id="config-callback-transport-failure",
        plugin_ref="config_file.config",
        targets=("10.10.24.2",),
        params={"callback_subject": "receive_config_file_result"},
    )
    lease = RunLease(
        task_id=request.task_id,
        request_digest=request.digest,
        owner_id="pod-a",
        fence=5,
        expires_at=999999,
        attempt_id="run-attempt-1",
    )
    result = TargetCollectionResult(
        target="10.10.24.2",
        status="success",
        attempts=1,
        value={"status": "success"},
    )

    outcomes = await publisher.publish_batch(((request, result, lease),))

    assert metrics_called is False
    assert len(outcomes) == 1
    assert isinstance(next(iter(outcomes.values())), ConnectionError)


@pytest.mark.asyncio
async def test_buffered_publisher_can_run_multiple_publish_batches_concurrently():
    release = asyncio.Event()

    class ConcurrentDelegate:
        def __init__(self):
            self.active = 0
            self.peak_active = 0

        async def publish_batch(self, _items):
            self.active += 1
            self.peak_active = max(self.peak_active, self.active)
            try:
                await release.wait()
            finally:
                self.active -= 1

    delegate = ConcurrentDelegate()
    publisher = BufferedResultPublisher(
        delegate,
        capacity=8,
        batch_size=1,
        flush_interval_seconds=0.01,
        worker_count=4,
    )
    request = CollectionRequest(
        task_id="run-concurrent",
        plugin_ref="network",
        targets=tuple(f"10.0.0.{index}" for index in range(4)),
        params={},
    )
    lease = RunLease(request.task_id, request.digest, "pod-a", 1, 999999)
    receipts = [
        await publisher.enqueue(
            request,
            TargetCollectionResult(
                target=f"10.0.0.{index}",
                status="success",
                attempts=1,
                value="metric 1",
            ),
            lease,
        )
        for index in range(4)
    ]

    for _ in range(100):
        if delegate.peak_active == 4:
            break
        await asyncio.sleep(0.001)

    assert delegate.peak_active == 4
    release.set()
    await asyncio.gather(*(receipt.wait() for receipt in receipts))
    await publisher.shutdown()


def test_scan_failures_require_delivery_collect_failures_do_not():
    scan_request = CollectionRequest(
        task_id="scan-family-run-5",
        plugin_ref="network.config",
        targets=("10.10.24.1",),
        params={"credential_result_subject": "receive_scan_credential_result"},
    )
    collect_request = CollectionRequest(
        task_id="collect-task-9",
        plugin_ref="network.config",
        targets=("10.10.24.1",),
        params={"credential_result_subject": "receive_collect_credential_result"},
    )
    failed = TargetCollectionResult(
        target="10.10.24.1",
        status="failed",
        attempts=1,
        error_code="authentication_failed",
    )
    assert _requires_delivery(scan_request, failed) is True
    assert _requires_delivery(collect_request, failed) is False


@pytest.mark.asyncio
async def test_scan_credential_result_publishes_success_and_failure():
    published = []
    batches = []

    async def publish_metrics_batch(entries):
        batches.append(entries)
        return {entry[2]["collection_result_id"]: None for entry in entries}

    async def publish_credential(result, params, task_id):
        published.append((dict(result), dict(params), task_id))

    publisher = NatsResultPublisher(
        metrics_publish_batch=publish_metrics_batch,
        credential_result_publish=publish_credential,
    )
    request = CollectionRequest(
        task_id="scan-family-run-5",
        plugin_ref="network.config",
        targets=("10.10.24.1", "10.10.24.2"),
        params={
            "collect_task_id": "5",
            "credential_result_subject": "receive_scan_credential_result",
            "snmp_port": "161",
        },
    )
    lease = RunLease(
        request.task_id,
        request.digest,
        "pod-a",
        3,
        999999,
        attempt_id="run-attempt-1",
    )

    await publisher.publish_batch(
        (
            (
                request,
                TargetCollectionResult(
                    target="10.10.24.1",
                    status="success",
                    attempts=1,
                    credential_id="credential-1",
                    value=StructuredMetricsPayload(
                        data={
                            "system": {
                                "sysobjectid": "1.3.6.1.4.1.9.1.1",
                                "sysname": "sw-core",
                                "port": 161,
                            }
                        }
                    ),
                ),
                lease,
            ),
            (
                request,
                TargetCollectionResult(
                    target="10.10.24.2",
                    status="unreachable",
                    attempts=0,
                    error_code="target_unreachable",
                ),
                lease,
            ),
        )
    )

    assert len(batches) == 1
    assert len(published) == 2
    success_event, success_params, success_task_id = published[0]
    failure_event, _, failure_task_id = published[1]
    assert success_task_id == failure_task_id == "scan-family-run-5"
    assert success_params["credential_result_subject"] == "receive_scan_credential_result"
    assert success_event["host"] == "10.10.24.1"
    assert success_event["credential_id"] == "credential-1"
    assert success_event["collect_task_id"] == "5"
    assert success_event["status"] == "success"
    assert success_event["producer"] == "stargazer"
    assert success_event["event_version"] == "2"
    assert success_event["finished_at"]
    assert success_event["port"] == 161
    assert success_event["snapshot"]["sysobjectid"] == "1.3.6.1.4.1.9.1.1"
    assert success_event["snapshot"]["sysname"] == "sw-core"
    assert failure_event["host"] == "10.10.24.2"
    assert failure_event["status"] == "unreachable"
    assert failure_event["port"] == 161
    assert failure_event["snapshot"]["host"] == "10.10.24.2"


def test_scan_credential_snapshot_unwraps_network_system_and_host_buckets():
    network_request = CollectionRequest(
        task_id="scan-network",
        plugin_ref="network.config",
        targets=("10.10.69.248",),
        params={"snmp_port": "161"},
    )
    network_snapshot, network_port = NatsResultPublisher._extract_scan_snapshot(
        network_request,
        TargetCollectionResult(
            target="10.10.69.248",
            status="success",
            attempts=1,
            value=StructuredMetricsPayload(
                data={
                    "network_system": [
                        {
                            "sysobjectid": "1.3.6.1.4.1.9.1.3210",
                            "sysname": "Catalyst-1200",
                            "sysdescr": "Cisco IOS",
                            "ip_addr": "10.10.69.248",
                            "port": 161,
                        }
                    ],
                    "network_interfaces": [{"index": "1"}],
                }
            ),
        ),
    )
    assert network_port == 161
    assert network_snapshot["sysobjectid"] == "1.3.6.1.4.1.9.1.3210"
    assert network_snapshot["sysname"] == "Catalyst-1200"
    assert network_snapshot["sysdescr"] == "Cisco IOS"

    host_request = CollectionRequest(
        task_id="scan-host",
        plugin_ref="host.config",
        targets=("10.11.27.147",),
        params={"port": "22"},
    )
    host_snapshot, host_port = NatsResultPublisher._extract_scan_snapshot(
        host_request,
        TargetCollectionResult(
            target="10.11.27.147",
            status="success",
            attempts=1,
            value=StructuredMetricsPayload(
                data={
                    "host": [
                        {
                            "hostname": "localhost",
                            "os_type": "Linux",
                            "os_name": "CentOS Linux",
                            "os_version": "7.9",
                            "ip_addr": "10.11.27.147",
                        }
                    ]
                }
            ),
        ),
    )
    assert host_port == 22
    assert host_snapshot["hostname"] == "localhost"
    assert host_snapshot["os_type"] == "Linux"
    assert host_snapshot["os_name"] == "CentOS Linux"
    assert host_snapshot["os_version"] == "7.9"
