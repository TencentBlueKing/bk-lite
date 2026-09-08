import pytest

from apps.cmdb.tasks import celery_tasks

pytestmark = pytest.mark.unit


def test_terminal_orchestrator_result_is_returned_without_retry(mocker):
    execute = mocker.patch(
        "apps.cmdb.services.first_collection_orchestrator.FirstCollectionOrchestrator.execute",
        return_value={"run_id": 12, "status": "accepted"},
    )
    retry = mocker.patch.object(celery_tasks.execute_first_collection_run, "retry")

    result = celery_tasks.execute_first_collection_run.run(12)

    assert result == {"run_id": 12, "status": "accepted"}
    execute.assert_called_once_with(12)
    retry.assert_not_called()


@pytest.mark.parametrize("retry_after", [10, 20])
def test_retry_wait_uses_orchestrator_backoff(mocker, retry_after):
    from celery.canvas import Signature
    from celery.exceptions import Retry

    mocker.patch(
        "apps.cmdb.services.first_collection_orchestrator.FirstCollectionOrchestrator.execute",
        return_value={"run_id": 12, "status": "retry_wait", "retry_after": retry_after},
    )
    apply_async = mocker.patch.object(Signature, "apply_async", autospec=True)
    celery_tasks.execute_first_collection_run.push_request(
        args=(12,),
        kwargs={},
        id=f"first-collection-retry-{retry_after}",
        retries=0 if retry_after == 10 else 1,
        called_directly=False,
        is_eager=False,
    )
    try:
        with pytest.raises(Retry) as retry_error:
            celery_tasks.execute_first_collection_run.run(12)
    finally:
        celery_tasks.execute_first_collection_run.pop_request()

    assert retry_error.value.when == retry_after
    assert apply_async.call_args.args[0].options["countdown"] == retry_after


def test_first_collection_task_never_calls_legacy_stargazer_trigger(mocker):
    legacy_trigger = mocker.patch("apps.cmdb.services.stargazer_collect_trigger.StargazerCollectTriggerClient.trigger")
    mocker.patch(
        "apps.cmdb.services.first_collection_orchestrator.FirstCollectionOrchestrator.execute",
        return_value={"run_id": 12, "status": "failed"},
    )

    assert celery_tasks.execute_first_collection_run.run(12) == {
        "run_id": 12,
        "status": "failed",
    }
    legacy_trigger.assert_not_called()


def test_new_one_shot_task_uses_a_new_protocol_name_and_legacy_messages_are_safely_retired(mocker, caplog):
    legacy_trigger = mocker.patch("apps.cmdb.services.stargazer_collect_trigger.StargazerCollectTriggerClient.trigger")

    assert celery_tasks.execute_first_collection_run.name == "apps.cmdb.tasks.celery_tasks.execute_first_collection_run"
    assert celery_tasks.trigger_first_collection.run(7, "old-fingerprint", "create") == {
        "status": "retired",
        "task_id": 7,
        "reason": "create",
    }
    legacy_trigger.assert_not_called()
    records = [record for record in caplog.records if record.msg.startswith("event=first_collection_legacy_message_retired")]
    assert len(records) == 1
    assert records[0].levelname == "WARNING"
    assert records[0].args == (7, "LegacyMessage")
    assert records[0].getMessage() == (
        "event=first_collection_legacy_message_retired task_id=7 failed_stage=protocol_retired error_type=LegacyMessage"
    )


def test_first_collection_task_retry_budget_covers_the_node_lock_watchdog():
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator

    covered_seconds = celery_tasks.execute_first_collection_run.max_retries * FirstCollectionOrchestrator.LOCK_RETRY_AFTER_SECONDS

    assert celery_tasks.execute_first_collection_run.max_retries >= FirstCollectionOrchestrator.MAX_LOCK_RETRIES
    assert covered_seconds > 70


def test_first_collection_recovery_task_is_registered_and_bounded(mocker):
    from apps.cmdb.config import CELERY_BEAT_SCHEDULE

    recover = mocker.patch(
        "apps.cmdb.services.first_collection_orchestrator.FirstCollectionOrchestrator.recover",
        return_value={"scanned": 3, "dispatched": 2, "failed": 1},
    )

    assert celery_tasks.recover_first_collection_runs.run() == {
        "scanned": 3,
        "dispatched": 2,
        "failed": 1,
    }
    recover.assert_called_once_with()
    entry = CELERY_BEAT_SCHEDULE["recover_first_collection_runs"]
    assert entry["task"] == "apps.cmdb.tasks.celery_tasks.recover_first_collection_runs"
