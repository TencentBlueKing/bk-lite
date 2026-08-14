import pytest
from core.collection.contracts import CredentialFailureResult, TargetCollectionResult
from core.collection.result_publisher import NatsResultPublisher
from core.collection.runtime import CollectionRequest, RunLease


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
            credential_failures=(
                CredentialFailureResult("credential-1", "capability_denied"),
            ),
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
