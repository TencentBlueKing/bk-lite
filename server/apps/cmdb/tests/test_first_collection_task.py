import pytest

from apps.cmdb.constants.constants import CollectPluginTypes
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.tasks import celery_tasks as ct

pytestmark = pytest.mark.django_db


def create_task(**overrides):
    values = {
        "name": "first-collect",
        "task_type": CollectPluginTypes.HOST,
        "driver_type": "snmp",
        "model_id": "host",
        "is_interval": True,
        "cycle_value_type": "cycle",
        "cycle_value": "30",
        "instances": [{"inst_name": "host-1", "ip_addr": "10.0.0.1"}],
        "access_point": [{"id": "node-1"}],
        "params": {},
        "team": [1],
    }
    values.update(overrides)
    return CollectModels.objects.create(**values)


def test_current_fingerprint_triggers_client(mocker):
    task = create_task()
    mocker.patch(
        "apps.cmdb.services.first_collection_policy.FirstCollectionPolicy.is_eligible",
        return_value=True,
    )
    mocker.patch(
        "apps.cmdb.services.first_collection_policy.FirstCollectionPolicy.fingerprint",
        return_value="fp",
    )
    trigger = mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.StargazerCollectTriggerClient.trigger",
        return_value=mocker.Mock(status="accepted", total=1, accepted=1),
    )

    result = ct.trigger_first_collection.run(task.id, "fp", "create")

    assert result["status"] == "accepted"
    trigger.assert_called_once()


def test_stale_fingerprint_skips(mocker):
    task = create_task()
    mocker.patch(
        "apps.cmdb.services.first_collection_policy.FirstCollectionPolicy.fingerprint",
        return_value="new-fp",
    )
    trigger = mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.StargazerCollectTriggerClient.trigger"
    )

    assert ct.trigger_first_collection.run(task.id, "old-fp", "update:params")["status"] == "stale"
    trigger.assert_not_called()


def test_missing_ineligible_and_disabled_skip(mocker):
    assert ct.trigger_first_collection.run(999999, "fp", "create")["status"] == "missing"

    short = create_task(cycle_value="5")
    assert ct.trigger_first_collection.run(short.id, "fp", "create")["status"] == "ineligible"

    long_task = create_task(name="disabled")
    mocker.patch("apps.cmdb.constants.constants.CMDB_FIRST_COLLECTION_ENABLED", False)
    assert ct.trigger_first_collection.run(long_task.id, "fp", "create")["status"] == "disabled"


def test_first_retryable_error_uses_ten_second_backoff(mocker):
    task = create_task()
    mocker.patch(
        "apps.cmdb.services.first_collection_policy.FirstCollectionPolicy.is_eligible",
        return_value=True,
    )
    mocker.patch(
        "apps.cmdb.services.first_collection_policy.FirstCollectionPolicy.fingerprint",
        return_value="fp",
    )
    from apps.cmdb.services.stargazer_collect_trigger import StargazerCollectRetryableError

    mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.StargazerCollectTriggerClient.trigger",
        side_effect=StargazerCollectRetryableError("retryable"),
    )
    from celery.canvas import Signature
    from celery.exceptions import Retry

    apply_async = mocker.patch.object(Signature, "apply_async", autospec=True)
    ct.trigger_first_collection.push_request(
        args=(task.id, "fp", "create"),
        kwargs={},
        id="first-collection-retry-1",
        retries=0,
        called_directly=False,
        is_eager=False,
    )
    try:
        with pytest.raises(Retry) as retry_error:
            ct.trigger_first_collection.run(task.id, "fp", "create")
    finally:
        ct.trigger_first_collection.pop_request()

    scheduled_signature = apply_async.call_args.args[0]
    assert retry_error.value.when == 10
    assert scheduled_signature.options["countdown"] == 10
    assert scheduled_signature.options["retries"] == 1
    assert ct.trigger_first_collection.max_retries == 2


def test_second_retryable_error_uses_twenty_second_backoff(mocker):
    task = create_task()
    mocker.patch(
        "apps.cmdb.services.first_collection_policy.FirstCollectionPolicy.is_eligible",
        return_value=True,
    )
    mocker.patch(
        "apps.cmdb.services.first_collection_policy.FirstCollectionPolicy.fingerprint",
        return_value="fp",
    )
    from apps.cmdb.services.stargazer_collect_trigger import StargazerCollectRetryableError

    mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.StargazerCollectTriggerClient.trigger",
        side_effect=StargazerCollectRetryableError("retryable"),
    )
    from celery.canvas import Signature
    from celery.exceptions import Retry

    apply_async = mocker.patch.object(Signature, "apply_async", autospec=True)
    ct.trigger_first_collection.push_request(
        args=(task.id, "fp", "create"),
        kwargs={},
        id="first-collection-retry-2",
        retries=1,
        called_directly=False,
        is_eager=False,
    )
    try:
        with pytest.raises(Retry) as retry_error:
            ct.trigger_first_collection.run(task.id, "fp", "create")
    finally:
        ct.trigger_first_collection.pop_request()

    scheduled_signature = apply_async.call_args.args[0]
    assert retry_error.value.when == 20
    assert scheduled_signature.options["countdown"] == 20
    assert scheduled_signature.options["retries"] == 2


def test_third_retryable_error_returns_exhausted_result_without_rescheduling(
    mocker, caplog
):
    task = create_task()
    mocker.patch(
        "apps.cmdb.services.first_collection_policy.FirstCollectionPolicy.is_eligible",
        return_value=True,
    )
    mocker.patch(
        "apps.cmdb.services.first_collection_policy.FirstCollectionPolicy.fingerprint",
        return_value="fp",
    )
    from apps.cmdb.services.stargazer_collect_trigger import StargazerCollectRetryableError

    mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.StargazerCollectTriggerClient.trigger",
        side_effect=StargazerCollectRetryableError(
            "token=top-secret broker=nats://user:password@broker.internal:4222"
        ),
    )
    from celery.canvas import Signature

    apply_async = mocker.patch.object(Signature, "apply_async", autospec=True)
    ct.trigger_first_collection.push_request(
        args=(task.id, "fp", "create"),
        kwargs={},
        id="first-collection-retry-3",
        retries=2,
        called_directly=False,
        is_eager=False,
    )
    try:
        with caplog.at_level("WARNING"):
            result = ct.trigger_first_collection.run(task.id, "fp", "create")
    finally:
        ct.trigger_first_collection.pop_request()

    apply_async.assert_not_called()
    assert result == {
        "status": "failed",
        "task_id": task.id,
        "reason": "create",
        "retry_exhausted": True,
    }
    assert "result=failed" in caplog.text
    assert "retry_exhausted=true" in caplog.text
    assert "top-secret" not in caplog.text
    assert "nats://" not in caplog.text
    assert "password" not in caplog.text
    assert ct.trigger_first_collection.max_retries == 2


def test_permanent_error_does_not_retry(mocker):
    task = create_task()
    mocker.patch(
        "apps.cmdb.services.first_collection_policy.FirstCollectionPolicy.is_eligible",
        return_value=True,
    )
    mocker.patch(
        "apps.cmdb.services.first_collection_policy.FirstCollectionPolicy.fingerprint",
        return_value="fp",
    )
    from apps.cmdb.services.stargazer_collect_trigger import StargazerCollectPermanentError

    mocker.patch(
        "apps.cmdb.services.stargazer_collect_trigger.StargazerCollectTriggerClient.trigger",
        side_effect=StargazerCollectPermanentError("HTTP 400"),
    )
    retry = mocker.patch.object(ct.trigger_first_collection, "retry")

    result = ct.trigger_first_collection.run(task.id, "fp", "create")

    assert result == {"status": "failed", "task_id": task.id, "reason": "create"}
    retry.assert_not_called()
