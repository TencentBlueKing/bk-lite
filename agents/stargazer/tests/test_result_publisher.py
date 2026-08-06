import pytest

from core.collection_runtime import CollectionRequest, RunLease
from core.result_publisher import NatsResultPublisher
from core.target_collection_executor import TargetCollectionResult


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
