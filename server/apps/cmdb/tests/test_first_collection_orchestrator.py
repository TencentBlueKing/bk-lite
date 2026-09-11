from datetime import timedelta

import pytest
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.cmdb.constants.constants import CollectPluginTypes
from apps.cmdb.models.collect_model import CollectModels

pytestmark = pytest.mark.django_db


def create_collect_task(**overrides):
    values = {
        "name": "first-collection-oneshot",
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


def test_same_task_fingerprint_creates_one_waiting_trigger_intent(mocker):
    from apps.cmdb.models.first_collection_run import FirstCollectionRun
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator

    task = create_collect_task()
    mocker.patch(
        "apps.cmdb.services.first_collection_policy.FirstCollectionPolicy.fingerprint",
        return_value="f" * 64,
    )

    first = FirstCollectionOrchestrator.schedule(task, reason="create")
    second = FirstCollectionOrchestrator.schedule(task, reason="create")

    assert first.id == second.id
    assert FirstCollectionRun.objects.count() == 1
    assert first.status == FirstCollectionRun.STATUS_WAITING_CONFIG
    assert first.channel_results == {
        f"cmdb_{task.id}": {
            "status": "pending",
            "task_id": "",
            "retryable": True,
        }
    }
    assert task.exec_status == CollectModels.objects.get(id=task.id).exec_status


def test_returning_to_an_earlier_configuration_creates_a_new_run(mocker):
    from apps.cmdb.models.first_collection_run import FirstCollectionRun
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator

    task = create_collect_task()
    first = FirstCollectionOrchestrator.schedule(task, reason="create")
    FirstCollectionRun.objects.filter(id=first.id).update(status=FirstCollectionRun.STATUS_ACCEPTED)

    version_a = CollectModels.objects.get(id=task.id)
    task.timeout += 1
    task.save()
    second = FirstCollectionOrchestrator.schedule(task, old_task=version_a, reason="update")
    FirstCollectionRun.objects.filter(id=second.id).update(status=FirstCollectionRun.STATUS_ACCEPTED)

    version_b = CollectModels.objects.get(id=task.id)
    task.timeout = version_a.timeout
    task.save()
    returned = FirstCollectionOrchestrator.schedule(task, old_task=version_b, reason="update")
    send_task = mocker.patch("apps.cmdb.services.first_collection_orchestrator.current_app.send_task")
    FirstCollectionOrchestrator.mark_config_ready_and_dispatch(returned.id)

    assert returned.id not in {first.id, second.id}
    assert returned.status == FirstCollectionRun.STATUS_WAITING_CONFIG
    send_task.assert_called_once_with(FirstCollectionOrchestrator.CELERY_TASK, args=[returned.id])


@pytest.mark.parametrize("old_status", ["pending", "waiting_config"])
def test_queued_old_revision_is_skipped_after_configuration_returns_to_a(mocker, old_status):
    from apps.cmdb.models.first_collection_run import FirstCollectionRun
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator

    task = create_collect_task()
    original = FirstCollectionOrchestrator.schedule(task)
    FirstCollectionRun.objects.filter(id=original.id).update(status=old_status, updated_at=timezone.now() - timedelta(minutes=2))
    version_a = CollectModels.objects.get(id=task.id)
    task.timeout += 1
    task.save()
    FirstCollectionOrchestrator.schedule(task, old_task=version_a)
    version_b = CollectModels.objects.get(id=task.id)
    task.timeout = version_a.timeout
    task.save()
    current = FirstCollectionOrchestrator.schedule(task, old_task=version_b)
    node_mgmt = mocker.patch("apps.cmdb.services.first_collection_orchestrator.NodeMgmt")
    push = mocker.patch("apps.cmdb.services.collect_service.CollectModelService.push_butch_node_params")
    delete = mocker.patch("apps.cmdb.services.collect_service.CollectModelService.delete_butch_node_params")
    mocker.patch("apps.cmdb.services.first_collection_orchestrator.current_app.send_task")

    if old_status == "waiting_config":
        FirstCollectionOrchestrator.recover()
    else:
        assert FirstCollectionOrchestrator.execute(original.id) == {"run_id": original.id, "status": "stale"}
    original.refresh_from_db()
    assert original.status == "skipped"
    assert original.failed_stage == "stale"
    node_mgmt.assert_not_called()
    push.assert_not_called()
    delete.assert_not_called()

    FirstCollectionRun.objects.filter(id=current.id).update(status="pending")
    node_mgmt.return_value.run_telegraf_child_configs_once.return_value = {
        "channels": {f"cmdb_{task.id}": {"status": "accepted", "task_id": "current-run", "retryable": False}},
    }
    assert FirstCollectionOrchestrator.execute(current.id)["status"] == "accepted"


def test_governance_edit_keeps_pending_first_collection_valid(mocker):
    from apps.cmdb.models.first_collection_run import FirstCollectionRun
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator

    task = create_collect_task()
    run = FirstCollectionOrchestrator.schedule(task)
    FirstCollectionRun.objects.filter(id=run.id).update(status="pending")
    previous = CollectModels.objects.get(id=task.id)
    task.name = "renamed"
    task.save()
    assert FirstCollectionOrchestrator.schedule(task, old_task=previous) is None
    node_mgmt = mocker.patch("apps.cmdb.services.first_collection_orchestrator.NodeMgmt")
    node_mgmt.return_value.run_telegraf_child_configs_once.return_value = {
        "channels": {f"cmdb_{task.id}": {"status": "accepted", "task_id": "original-run", "retryable": False}},
    }
    assert FirstCollectionOrchestrator.execute(run.id)["status"] == "accepted"


@pytest.mark.parametrize(
    ("device_minutes", "topology_minutes", "topology_enabled", "suffixes"),
    [
        (5, 30, True, ["_topology"]),
        (30, 5, True, [""]),
        (15, 15, True, ["", "_topology"]),
        (5, None, True, ["_topology"]),
        (2, None, True, []),
        (5, 30, False, []),
        (30, 30, False, [""]),
    ],
)
def test_network_first_collection_dispatches_only_long_interval_channels(mocker, device_minutes, topology_minutes, topology_enabled, suffixes):
    from apps.cmdb.models.first_collection_run import FirstCollectionRun
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator

    task = create_collect_task(
        task_type="snmp",
        model_id="network",
        cycle_value=str(device_minutes),
        params={"has_network_topo": topology_enabled, "topology_interval_minutes": topology_minutes},
    )
    run = FirstCollectionOrchestrator.schedule(task)
    expected_ids = [f"cmdb_{task.id}{suffix}" for suffix in suffixes]
    if not expected_ids:
        assert run is None
        return
    assert list(run.channel_results) == expected_ids
    FirstCollectionRun.objects.filter(id=run.id).update(status="pending")
    node_mgmt = mocker.patch("apps.cmdb.services.first_collection_orchestrator.NodeMgmt")
    node_mgmt.return_value.run_telegraf_child_configs_once.return_value = {
        "channels": {config_id: {"status": "accepted", "task_id": f"accepted-{config_id}", "retryable": False} for config_id in expected_ids},
    }
    assert FirstCollectionOrchestrator.execute(run.id)["status"] == "accepted"
    assert node_mgmt.return_value.run_telegraf_child_configs_once.call_args.kwargs["config_ids"] == expected_ids


def test_outer_transaction_rollback_removes_intent_and_never_dispatches(mocker):
    from apps.cmdb.models.first_collection_run import FirstCollectionRun
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator

    task = create_collect_task()
    dispatch = mocker.patch.object(FirstCollectionOrchestrator, "mark_config_ready_and_dispatch")

    with pytest.raises(RuntimeError, match="rollback"), transaction.atomic():
        run = FirstCollectionOrchestrator.schedule(task, reason="create")
        transaction.on_commit(lambda: dispatch(run.id))
        raise RuntimeError("rollback")

    assert not FirstCollectionRun.objects.filter(collect_task=task).exists()
    dispatch.assert_not_called()


def test_config_ready_persists_pending_before_dispatch(mocker):
    from apps.cmdb.models.first_collection_run import FirstCollectionRun
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator

    task = create_collect_task()
    run = FirstCollectionOrchestrator.schedule(task, reason="create")
    observed_statuses = []

    def observe_dispatch(_task_name, args):
        observed_statuses.append(FirstCollectionRun.objects.get(id=args[0]).status)

    send_task = mocker.patch(
        "apps.cmdb.services.first_collection_orchestrator.current_app.send_task",
        side_effect=observe_dispatch,
    )

    result = FirstCollectionOrchestrator.mark_config_ready_and_dispatch(run.id)

    assert result.status == FirstCollectionRun.STATUS_PENDING
    assert observed_statuses == [FirstCollectionRun.STATUS_PENDING]
    send_task.assert_called_once_with(
        FirstCollectionOrchestrator.CELERY_TASK,
        args=[run.id],
    )


def test_execute_accepts_one_shot_without_changing_collect_task_status(mocker):
    from apps.cmdb.models.first_collection_run import FirstCollectionRun
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator

    task = create_collect_task()
    original_exec_status = task.exec_status
    run = FirstCollectionOrchestrator.schedule(task, reason="create")
    mocker.patch("apps.cmdb.services.first_collection_orchestrator.current_app.send_task")
    FirstCollectionOrchestrator.mark_config_ready_and_dispatch(run.id)
    node_mgmt = mocker.patch("apps.cmdb.services.first_collection_orchestrator.NodeMgmt")
    node_mgmt.return_value.run_telegraf_child_configs_once.return_value = {
        "request_id": f"first-collection-{run.id}",
        "status": "accepted",
        "channels": {
            f"cmdb_{task.id}": {
                "status": "accepted",
                "task_id": "stargazer-task-1",
                "retryable": False,
            }
        },
    }

    result = FirstCollectionOrchestrator.execute(run.id)

    run.refresh_from_db()
    task.refresh_from_db()
    assert result == {"run_id": run.id, "status": "accepted"}
    assert run.status == FirstCollectionRun.STATUS_ACCEPTED
    assert run.attempt == 1
    assert run.channel_results[f"cmdb_{task.id}"]["task_id"] == "stargazer-task-1"
    assert task.exec_status == original_exec_status


def test_claim_locks_only_run_row_without_nullable_outer_join(mocker):
    """PostgreSQL rejects FOR UPDATE when its query contains the nullable task outer join."""
    from apps.cmdb.models.first_collection_run import FirstCollectionRun
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator

    task = create_collect_task()
    run = FirstCollectionOrchestrator.schedule(task, reason="create")
    FirstCollectionRun.objects.filter(id=run.id).update(status=FirstCollectionRun.STATUS_PENDING)
    node_mgmt = mocker.patch("apps.cmdb.services.first_collection_orchestrator.NodeMgmt")
    node_mgmt.return_value.run_telegraf_child_configs_once.return_value = {
        "status": "accepted",
        "channels": {
            f"cmdb_{task.id}": {
                "status": "accepted",
                "task_id": "stargazer-task",
                "retryable": False,
            }
        },
    }

    with CaptureQueriesContext(connection) as captured:
        assert FirstCollectionOrchestrator.execute(run.id)["status"] == FirstCollectionRun.STATUS_ACCEPTED

    claim_queries = [item["sql"] for item in captured.captured_queries if "cmdb_firstcollectionrun" in item["sql"] and "LIMIT 1" in item["sql"]]
    assert claim_queries
    assert "LEFT OUTER JOIN" not in claim_queries[0].upper()


def test_partial_network_retry_only_executes_unaccepted_channel(mocker):
    from apps.cmdb.models.first_collection_run import FirstCollectionRun
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator

    task = create_collect_task(
        task_type=CollectPluginTypes.SNMP,
        model_id="network",
        params={"has_network_topo": True},
    )
    run = FirstCollectionOrchestrator.schedule(task, reason="create")
    mocker.patch("apps.cmdb.services.first_collection_orchestrator.current_app.send_task")
    FirstCollectionOrchestrator.mark_config_ready_and_dispatch(run.id)
    node_mgmt = mocker.patch("apps.cmdb.services.first_collection_orchestrator.NodeMgmt")
    node_mgmt.return_value.run_telegraf_child_configs_once.side_effect = [
        {
            "status": "partial",
            "channels": {
                f"cmdb_{task.id}": {
                    "status": "accepted",
                    "task_id": "device-task",
                    "retryable": False,
                },
                f"cmdb_{task.id}_topology": {
                    "status": "failed",
                    "task_id": "",
                    "retryable": True,
                },
            },
        },
        {
            "status": "accepted",
            "channels": {
                f"cmdb_{task.id}_topology": {
                    "status": "duplicate_active",
                    "task_id": "topology-task",
                    "retryable": False,
                }
            },
        },
    ]

    assert FirstCollectionOrchestrator.execute(run.id) == {
        "run_id": run.id,
        "status": FirstCollectionRun.STATUS_RETRY_WAIT,
        "retry_after": 10,
    }
    assert FirstCollectionOrchestrator.execute(run.id) == {
        "run_id": run.id,
        "status": FirstCollectionRun.STATUS_ACCEPTED,
    }

    second_request = node_mgmt.return_value.run_telegraf_child_configs_once.call_args_list[1].kwargs
    assert second_request["config_ids"] == [f"cmdb_{task.id}_topology"]
    run.refresh_from_db()
    assert run.attempt == 2
    assert run.channel_results[f"cmdb_{task.id}"]["task_id"] == "device-task"
    assert run.channel_results[f"cmdb_{task.id}_topology"]["status"] == "duplicate_active"


def test_celery_task_retries_same_run_with_orchestrator_backoff(mocker):
    from celery.canvas import Signature
    from celery.exceptions import Retry

    from apps.cmdb.tasks import celery_tasks

    execute = mocker.patch(
        "apps.cmdb.services.first_collection_orchestrator.FirstCollectionOrchestrator.execute",
        return_value={"run_id": 19, "status": "retry_wait", "retry_after": 10},
    )
    apply_async = mocker.patch.object(Signature, "apply_async", autospec=True)
    celery_tasks.execute_first_collection_run.push_request(
        args=(19,),
        kwargs={},
        id="first-collection-run-19",
        retries=0,
        called_directly=False,
        is_eager=False,
    )
    try:
        with pytest.raises(Retry) as retry_error:
            celery_tasks.execute_first_collection_run.run(19)
    finally:
        celery_tasks.execute_first_collection_run.pop_request()

    assert retry_error.value.when == 10
    assert apply_async.call_args.args[0].options["countdown"] == 10
    execute.assert_called_once_with(19)


def test_expired_worker_cannot_overwrite_new_worker_result(mocker):
    from apps.cmdb.models.first_collection_run import FirstCollectionRun
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator

    task = create_collect_task()
    run = FirstCollectionOrchestrator.schedule(task, reason="create")
    mocker.patch("apps.cmdb.services.first_collection_orchestrator.current_app.send_task")
    FirstCollectionOrchestrator.mark_config_ready_and_dispatch(run.id)
    node_mgmt = mocker.patch("apps.cmdb.services.first_collection_orchestrator.NodeMgmt")

    accepted = {
        "status": "accepted",
        "channels": {
            f"cmdb_{task.id}": {
                "status": "accepted",
                "task_id": "new-worker-task",
                "retryable": False,
            }
        },
    }

    def expire_and_run_new_worker(**_kwargs):
        FirstCollectionRun.objects.filter(id=run.id).update(lease_expires_at=timezone.now())
        node_mgmt.return_value.run_telegraf_child_configs_once.side_effect = None
        node_mgmt.return_value.run_telegraf_child_configs_once.return_value = accepted
        assert FirstCollectionOrchestrator.execute(run.id)["status"] == FirstCollectionRun.STATUS_ACCEPTED
        return {
            "status": "failed",
            "channels": {
                f"cmdb_{task.id}": {
                    "status": "failed",
                    "task_id": "",
                    "retryable": True,
                }
            },
        }

    node_mgmt.return_value.run_telegraf_child_configs_once.side_effect = expire_and_run_new_worker

    assert FirstCollectionOrchestrator.execute(run.id) == {
        "run_id": run.id,
        "status": "stale_worker",
    }
    run.refresh_from_db()
    assert run.status == FirstCollectionRun.STATUS_ACCEPTED
    assert run.attempt == 2
    assert run.channel_results[f"cmdb_{task.id}"]["task_id"] == "new-worker-task"


def test_terminal_run_is_not_dispatched_again(mocker):
    from apps.cmdb.models.first_collection_run import FirstCollectionRun
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator

    task = create_collect_task()
    run = FirstCollectionOrchestrator.schedule(task, reason="create")
    FirstCollectionRun.objects.filter(id=run.id).update(status=FirstCollectionRun.STATUS_ACCEPTED)
    send_task = mocker.patch("apps.cmdb.services.first_collection_orchestrator.current_app.send_task")

    result = FirstCollectionOrchestrator.mark_config_ready_and_dispatch(run.id)

    assert result.status == FirstCollectionRun.STATUS_ACCEPTED
    send_task.assert_not_called()


def test_recovery_pushes_waiting_config_then_dispatches(mocker):
    from apps.cmdb.models.first_collection_run import FirstCollectionRun
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator

    task = create_collect_task()
    run = FirstCollectionOrchestrator.schedule(task, reason="create")
    FirstCollectionRun.objects.filter(id=run.id).update(
        updated_at=timezone.now() - FirstCollectionOrchestrator.RECOVERY_STALE_AFTER,
    )
    events = []
    mocker.patch(
        "apps.cmdb.services.collect_service.CollectModelService.delete_butch_node_params",
        side_effect=lambda recovered_task: events.append(f"delete:{recovered_task.id}"),
    )
    mocker.patch(
        "apps.cmdb.services.collect_service.CollectModelService.push_butch_node_params",
        side_effect=lambda recovered_task: events.append(f"push:{recovered_task.id}"),
    )
    mocker.patch(
        "apps.cmdb.services.first_collection_orchestrator.current_app.send_task",
        side_effect=lambda _name, args: events.append(f"dispatch:{args[0]}"),
    )

    result = FirstCollectionOrchestrator.recover()

    run.refresh_from_db()
    assert result == {"scanned": 1, "dispatched": 1, "failed": 0}
    assert events == [f"delete:{task.id}", f"push:{task.id}", f"dispatch:{run.id}"]
    assert run.status == FirstCollectionRun.STATUS_PENDING


def test_recovery_replaces_an_already_saved_config_after_lost_ack(mocker):
    """A lost config RPC response leaves the config saved and the run waiting."""
    from apps.cmdb.models.first_collection_run import FirstCollectionRun
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator

    task = create_collect_task()
    run = FirstCollectionOrchestrator.schedule(task, reason="create")
    FirstCollectionRun.objects.filter(id=run.id).update(
        updated_at=timezone.now() - FirstCollectionOrchestrator.RECOVERY_STALE_AFTER,
    )
    config_state = {"exists": True}

    def delete_config(_task):
        config_state["exists"] = False

    def create_config(_task):
        if config_state["exists"]:
            raise RuntimeError("duplicate child config")
        config_state["exists"] = True

    mocker.patch(
        "apps.cmdb.services.collect_service.CollectModelService.delete_butch_node_params",
        side_effect=delete_config,
    )
    mocker.patch(
        "apps.cmdb.services.collect_service.CollectModelService.push_butch_node_params",
        side_effect=create_config,
    )
    send_task = mocker.patch("apps.cmdb.services.first_collection_orchestrator.current_app.send_task")

    result = FirstCollectionOrchestrator.recover()

    run.refresh_from_db()
    assert result == {"scanned": 1, "dispatched": 1, "failed": 0}
    assert config_state["exists"] is True
    assert run.status == FirstCollectionRun.STATUS_PENDING
    send_task.assert_called_once_with(FirstCollectionOrchestrator.CELERY_TASK, args=[run.id])


def test_recovery_redispatches_stale_pending_without_rewriting_config(mocker):
    from apps.cmdb.models.first_collection_run import FirstCollectionRun
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator

    task = create_collect_task()
    run = FirstCollectionOrchestrator.schedule(task, reason="create")
    FirstCollectionRun.objects.filter(id=run.id).update(
        status=FirstCollectionRun.STATUS_PENDING,
        updated_at=timezone.now() - FirstCollectionOrchestrator.RECOVERY_STALE_AFTER,
    )
    push = mocker.patch("apps.cmdb.services.collect_service.CollectModelService.push_butch_node_params")
    send_task = mocker.patch("apps.cmdb.services.first_collection_orchestrator.current_app.send_task")

    result = FirstCollectionOrchestrator.recover()

    assert result == {"scanned": 1, "dispatched": 1, "failed": 0}
    push.assert_not_called()
    send_task.assert_called_once_with(FirstCollectionOrchestrator.CELERY_TASK, args=[run.id])


def test_failed_dispatch_rotates_the_bounded_recovery_window(mocker, monkeypatch):
    from apps.cmdb.models.first_collection_run import FirstCollectionRun
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator

    runs = []
    stale_at = timezone.now() - FirstCollectionOrchestrator.RECOVERY_STALE_AFTER
    for index in range(2):
        task_instance = create_collect_task(name=f"dispatch-recovery-{index}")
        run = FirstCollectionOrchestrator.schedule(task_instance, reason="create")
        FirstCollectionRun.objects.filter(id=run.id).update(
            status=FirstCollectionRun.STATUS_PENDING,
            updated_at=stale_at - timedelta(seconds=2 - index),
        )
        runs.append(run)
    monkeypatch.setattr(FirstCollectionOrchestrator, "RECOVERY_LIMIT", 1)
    attempted_run_ids = []

    def fail_dispatch(_task_name, *, args):
        attempted_run_ids.append(args[0])
        raise RuntimeError("broker unavailable")

    mocker.patch(
        "apps.cmdb.services.first_collection_orchestrator.current_app.send_task",
        side_effect=fail_dispatch,
    )

    assert FirstCollectionOrchestrator.recover() == {"scanned": 1, "dispatched": 0, "failed": 1}
    assert FirstCollectionOrchestrator.recover() == {"scanned": 1, "dispatched": 0, "failed": 1}
    assert attempted_run_ids == [runs[0].id, runs[1].id]


def test_dispatch_recovery_stops_after_bounded_attempts(mocker):
    from apps.cmdb.models.first_collection_run import FirstCollectionRun
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator

    task_instance = create_collect_task()
    run = FirstCollectionOrchestrator.schedule(task_instance, reason="create")
    FirstCollectionRun.objects.filter(id=run.id).update(status=FirstCollectionRun.STATUS_PENDING)
    send_task = mocker.patch(
        "apps.cmdb.services.first_collection_orchestrator.current_app.send_task",
        side_effect=RuntimeError("broker unavailable"),
    )

    for _index in range(FirstCollectionOrchestrator.MAX_DISPATCH_ATTEMPTS):
        FirstCollectionRun.objects.filter(id=run.id).update(
            updated_at=timezone.now() - FirstCollectionOrchestrator.RECOVERY_STALE_AFTER,
        )
        assert FirstCollectionOrchestrator.recover()["failed"] == 1

    run.refresh_from_db()
    assert run.status == FirstCollectionRun.STATUS_FAILED
    assert run.dispatch_attempt == FirstCollectionOrchestrator.MAX_DISPATCH_ATTEMPTS
    assert run.failed_stage == "dispatch"
    assert run.finished_at is not None
    assert send_task.call_count == FirstCollectionOrchestrator.MAX_DISPATCH_ATTEMPTS

    FirstCollectionRun.objects.filter(id=run.id).update(
        updated_at=timezone.now() - FirstCollectionOrchestrator.RECOVERY_STALE_AFTER,
    )
    assert FirstCollectionOrchestrator.recover()["scanned"] == 0


def test_fingerprint_change_skips_stale_run_without_node_execution(mocker, caplog):
    from apps.cmdb.models.first_collection_run import FirstCollectionRun
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator

    task = create_collect_task()
    run = FirstCollectionOrchestrator.schedule(task, reason="create")
    FirstCollectionRun.objects.filter(id=run.id).update(status=FirstCollectionRun.STATUS_PENDING)
    task.timeout += 1
    task.save(update_fields=["timeout"])
    node_mgmt = mocker.patch("apps.cmdb.services.first_collection_orchestrator.NodeMgmt")

    assert FirstCollectionOrchestrator.execute(run.id) == {
        "run_id": run.id,
        "status": "stale",
    }
    run.refresh_from_db()
    assert run.status == FirstCollectionRun.STATUS_SKIPPED
    assert run.failed_stage == "stale"
    node_mgmt.assert_not_called()
    records = [record for record in caplog.records if record.msg.startswith("event=first_collection_skipped")]
    assert len(records) == 1
    assert records[0].levelname == "WARNING"
    assert records[0].args == (run.id, task.id, "stale", "PolicySkip")
    assert records[0].getMessage() == (f"event=first_collection_skipped run_id={run.id} task_id={task.id} failed_stage=stale error_type=PolicySkip")


def test_permanent_channel_failure_finishes_without_retry_and_records_stage(mocker, caplog):
    from apps.cmdb.models.first_collection_run import FirstCollectionRun
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator

    task = create_collect_task()
    run = FirstCollectionOrchestrator.schedule(task, reason="create")
    FirstCollectionRun.objects.filter(id=run.id).update(status=FirstCollectionRun.STATUS_PENDING)
    node_mgmt = mocker.patch("apps.cmdb.services.first_collection_orchestrator.NodeMgmt")
    node_mgmt.return_value.run_telegraf_child_configs_once.return_value = {
        "status": "failed",
        "channels": {
            f"cmdb_{task.id}": {
                "status": "failed",
                "task_id": "",
                "retryable": False,
                "error_type": "TelegrafOneShotError",
            }
        },
    }

    assert FirstCollectionOrchestrator.execute(run.id) == {
        "run_id": run.id,
        "status": FirstCollectionRun.STATUS_FAILED,
    }
    run.refresh_from_db()
    assert run.attempt == 1
    assert run.failed_stage == "one_shot"
    assert run.error_type == "TelegrafOneShotError"
    records = [record for record in caplog.records if record.msg.startswith("event=first_collection_attempt_finished")]
    assert len(records) == 1
    assert records[0].levelname == "WARNING"
    assert records[0].args == (run.id, task.id, 1, "failed", "one_shot", "TelegrafOneShotError")
    assert records[0].getMessage() == (
        f"event=first_collection_attempt_finished run_id={run.id} task_id={task.id} "
        "attempt=1 result=failed failed_stage=one_shot error_type=TelegrafOneShotError"
    )


def test_network_retry_exhaustion_finishes_partial_and_preserves_accepted_channel(mocker):
    from apps.cmdb.models.first_collection_run import FirstCollectionRun
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator

    task = create_collect_task(
        task_type=CollectPluginTypes.SNMP,
        model_id="network",
        params={"has_network_topo": True},
    )
    run = FirstCollectionOrchestrator.schedule(task, reason="create")
    FirstCollectionRun.objects.filter(id=run.id).update(status=FirstCollectionRun.STATUS_PENDING)
    node_mgmt = mocker.patch("apps.cmdb.services.first_collection_orchestrator.NodeMgmt")
    node_mgmt.return_value.run_telegraf_child_configs_once.return_value = {
        "status": "partial",
        "channels": {
            f"cmdb_{task.id}": {
                "status": "accepted",
                "task_id": "device-task",
                "retryable": False,
            },
            f"cmdb_{task.id}_topology": {
                "status": "failed",
                "task_id": "",
                "retryable": True,
                "error_type": "TimeoutError",
            },
        },
    }

    assert FirstCollectionOrchestrator.execute(run.id)["retry_after"] == 10
    assert FirstCollectionOrchestrator.execute(run.id)["retry_after"] == 20
    assert FirstCollectionOrchestrator.execute(run.id) == {
        "run_id": run.id,
        "status": FirstCollectionRun.STATUS_PARTIAL,
    }

    run.refresh_from_db()
    assert run.attempt == 3
    assert run.failed_stage == "one_shot"
    assert run.error_type == "TimeoutError"
    assert run.channel_results[f"cmdb_{task.id}"]["task_id"] == "device-task"
    assert all(
        call.kwargs["config_ids"] == [f"cmdb_{task.id}_topology"]
        for call in node_mgmt.return_value.run_telegraf_child_configs_once.call_args_list[1:]
    )


def test_node_lock_contention_retries_without_consuming_collection_attempt(mocker):
    from apps.cmdb.models.first_collection_run import FirstCollectionRun
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator

    task = create_collect_task()
    run = FirstCollectionOrchestrator.schedule(task, reason="create")
    FirstCollectionRun.objects.filter(id=run.id).update(status=FirstCollectionRun.STATUS_PENDING)
    node_mgmt = mocker.patch("apps.cmdb.services.first_collection_orchestrator.NodeMgmt")
    node_mgmt.return_value.run_telegraf_child_configs_once.return_value = {
        "status": "failed",
        "channels": {
            f"cmdb_{task.id}": {
                "status": "failed",
                "task_id": "",
                "retryable": True,
                "error_type": "NodeBusy",
            }
        },
    }

    for _index in range(FirstCollectionOrchestrator.MAX_LOCK_RETRIES):
        assert FirstCollectionOrchestrator.execute(run.id) == {
            "run_id": run.id,
            "status": FirstCollectionRun.STATUS_RETRY_WAIT,
            "retry_after": FirstCollectionOrchestrator.LOCK_RETRY_AFTER_SECONDS,
        }

    run.refresh_from_db()
    assert run.attempt == 0
    assert run.status == FirstCollectionRun.STATUS_RETRY_WAIT
    assert run.finished_at is None


@pytest.mark.parametrize("device_accepted", [False, True])
def test_node_busy_budget_survives_recovery_and_finishes_without_redispatch(mocker, device_accepted):
    from apps.cmdb.models.first_collection_run import FirstCollectionRun
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator
    from apps.cmdb.tasks.celery_tasks import execute_first_collection_run

    task = create_collect_task(task_type="snmp", model_id="network", params={"has_network_topo": device_accepted})
    run = FirstCollectionOrchestrator.schedule(task)
    channels = run.channel_results
    if device_accepted:
        channels[f"cmdb_{task.id}"] = {"status": "accepted", "task_id": "device-run", "retryable": False}
    FirstCollectionRun.objects.filter(id=run.id).update(status="pending", channel_results=channels)
    remaining_id = f"cmdb_{task.id}_topology" if device_accepted else f"cmdb_{task.id}"
    node_mgmt = mocker.patch("apps.cmdb.services.first_collection_orchestrator.NodeMgmt")
    node_mgmt.return_value.run_telegraf_child_configs_once.return_value = {
        "channels": {remaining_id: {"status": "failed", "retryable": True, "error_type": "NodeBusy"}},
    }
    dispatch = mocker.patch("apps.cmdb.services.first_collection_orchestrator.current_app.send_task")

    for index in range(8):
        assert FirstCollectionOrchestrator.execute(run.id)["status"] == "retry_wait"
        if index == 3:
            FirstCollectionRun.objects.filter(id=run.id).update(updated_at=timezone.now() - timedelta(minutes=2))
            assert FirstCollectionOrchestrator.recover()["dispatched"] == 1

    execute_first_collection_run.push_request(args=[run.id], kwargs={}, retries=8, called_directly=False, is_eager=False)
    try:
        result = execute_first_collection_run.run(run.id)
    finally:
        execute_first_collection_run.pop_request()

    terminal_status = "partial" if device_accepted else "failed"
    assert result == {"run_id": run.id, "status": terminal_status}
    run.refresh_from_db()
    assert run.attempt == 0
    assert run.status == terminal_status
    assert run.finished_at is not None
    assert run.error_type == "NodeBusy"
    if device_accepted:
        assert run.channel_results[f"cmdb_{task.id}"]["task_id"] == "device-run"
    FirstCollectionRun.objects.filter(id=run.id).update(updated_at=timezone.now() - timedelta(minutes=2))
    dispatch.reset_mock()
    assert FirstCollectionOrchestrator.recover()["dispatched"] == 0
    dispatch.assert_not_called()


def test_celery_preserves_business_attempts_after_eight_node_busy_retries(mocker):
    from celery.canvas import Signature
    from celery.exceptions import Retry

    from apps.cmdb.models.first_collection_run import FirstCollectionRun
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator
    from apps.cmdb.tasks.celery_tasks import execute_first_collection_run

    task = create_collect_task()
    run = FirstCollectionOrchestrator.schedule(task)
    FirstCollectionRun.objects.filter(id=run.id).update(status="pending")
    channel_id = f"cmdb_{task.id}"
    busy = {"channels": {channel_id: {"status": "failed", "retryable": True, "error_type": "NodeBusy"}}}
    unavailable = {"channels": {channel_id: {"status": "failed", "retryable": True, "error_type": "TimeoutError"}}}
    accepted = {"channels": {channel_id: {"status": "accepted", "retryable": False, "task_id": "accepted-run"}}}
    node_mgmt = mocker.patch("apps.cmdb.services.first_collection_orchestrator.NodeMgmt")
    node_mgmt.return_value.run_telegraf_child_configs_once.side_effect = [busy] * 8 + [unavailable] * 2 + [accepted]
    mocker.patch.object(Signature, "apply_async", autospec=True)

    for retries in range(11):
        execute_first_collection_run.push_request(args=[run.id], kwargs={}, retries=retries, called_directly=False, is_eager=False)
        try:
            if retries < 10:
                with pytest.raises(Retry):
                    execute_first_collection_run.run(run.id)
            else:
                assert execute_first_collection_run.run(run.id) == {"run_id": run.id, "status": "accepted"}
        finally:
            execute_first_collection_run.pop_request()
    run.refresh_from_db()
    assert run.attempt == 3


def test_node_mgmt_rpc_exception_has_one_safe_traceback_owner(mocker, caplog):
    from apps.cmdb.models.first_collection_run import FirstCollectionRun
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator

    task = create_collect_task()
    run = FirstCollectionOrchestrator.schedule(task, reason="create")
    FirstCollectionRun.objects.filter(id=run.id).update(status=FirstCollectionRun.STATUS_PENDING)
    node_mgmt = mocker.patch("apps.cmdb.services.first_collection_orchestrator.NodeMgmt")
    original_error = RuntimeError("password=credential-sentinel token=private-sentinel")
    node_mgmt.return_value.run_telegraf_child_configs_once.side_effect = original_error

    result = FirstCollectionOrchestrator.execute(run.id)

    assert result["status"] == FirstCollectionRun.STATUS_RETRY_WAIT
    run.refresh_from_db()
    assert run.failed_stage == "node_mgmt_rpc"
    assert run.error_type == "RuntimeError"
    records = [record for record in caplog.records if "event=first_collection_rpc_failed" in record.getMessage()]
    assert len(records) == 1
    assert records[0].msg == ("event=first_collection_rpc_failed run_id=%s task_id=%s failed_stage=node_mgmt_rpc error_type=%s")
    assert records[0].args == (run.id, task.id, "RuntimeError")
    assert records[0].getMessage() == (
        f"event=first_collection_rpc_failed run_id={run.id} task_id={task.id} failed_stage=node_mgmt_rpc error_type=RuntimeError"
    )
    assert records[0].exc_info[2] is original_error.__traceback__
    assert original_error.args == ("password=credential-sentinel token=private-sentinel",)
    assert "credential-sentinel" not in caplog.text
    assert "private-sentinel" not in caplog.text


def test_dispatch_failure_has_one_safe_traceback_and_preserves_pending_state(mocker, caplog):
    from apps.cmdb.models.first_collection_run import FirstCollectionRun
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator

    task = create_collect_task()
    run = FirstCollectionOrchestrator.schedule(task, reason="create")
    original_error = RuntimeError("password=dispatch-secret")
    mocker.patch(
        "apps.cmdb.services.first_collection_orchestrator.current_app.send_task",
        side_effect=original_error,
    )

    result = FirstCollectionOrchestrator.mark_config_ready_and_dispatch(run.id)

    result.refresh_from_db()
    assert result.status == FirstCollectionRun.STATUS_PENDING
    records = [record for record in caplog.records if record.msg.startswith("event=first_collection_dispatch_failed")]
    assert len(records) == 1
    assert records[0].msg == ("event=first_collection_dispatch_failed run_id=%s task_id=%s failed_stage=dispatch error_type=%s")
    assert records[0].args == (run.id, task.id, "RuntimeError")
    assert records[0].getMessage() == (
        f"event=first_collection_dispatch_failed run_id={run.id} task_id={task.id} failed_stage=dispatch error_type=RuntimeError"
    )
    assert records[0].exc_info[2] is original_error.__traceback__
    assert original_error.args == ("password=dispatch-secret",)
    assert "dispatch-secret" not in caplog.text


def test_recovery_failure_has_one_safe_traceback_and_keeps_waiting_config(mocker, caplog):
    from apps.cmdb.models.first_collection_run import FirstCollectionRun
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator

    task = create_collect_task()
    run = FirstCollectionOrchestrator.schedule(task, reason="create")
    FirstCollectionRun.objects.filter(id=run.id).update(
        updated_at=timezone.now() - FirstCollectionOrchestrator.RECOVERY_STALE_AFTER,
    )
    original_error = RuntimeError("token=recovery-secret")
    mocker.patch("apps.cmdb.services.collect_service.CollectModelService.delete_butch_node_params")
    mocker.patch(
        "apps.cmdb.services.collect_service.CollectModelService.push_butch_node_params",
        side_effect=original_error,
    )

    result = FirstCollectionOrchestrator.recover()

    run.refresh_from_db()
    assert result == {"scanned": 1, "dispatched": 0, "failed": 1}
    assert run.status == FirstCollectionRun.STATUS_WAITING_CONFIG
    records = [record for record in caplog.records if record.msg.startswith("event=first_collection_recovery_failed")]
    assert len(records) == 1
    assert records[0].msg == "event=first_collection_recovery_failed run_id=%s failed_stage=recovery error_type=%s"
    assert records[0].args == (run.id, "RuntimeError")
    assert records[0].getMessage() == (f"event=first_collection_recovery_failed run_id={run.id} failed_stage=recovery error_type=RuntimeError")
    assert records[0].exc_info[2] is original_error.__traceback__
    assert original_error.args == ("token=recovery-secret",)
    assert "recovery-secret" not in caplog.text


def test_failed_config_recovery_rotates_the_bounded_scan_window(mocker, monkeypatch):
    from apps.cmdb.models.first_collection_run import FirstCollectionRun
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator

    tasks = [create_collect_task(name=f"recovery-{index}") for index in range(3)]
    runs = [FirstCollectionOrchestrator.schedule(task, reason="create") for task in tasks]
    stale_at = timezone.now() - FirstCollectionOrchestrator.RECOVERY_STALE_AFTER
    for index, run in enumerate(runs):
        FirstCollectionRun.objects.filter(id=run.id).update(updated_at=stale_at - timedelta(seconds=3 - index))
    monkeypatch.setattr(FirstCollectionOrchestrator, "RECOVERY_LIMIT", 2)
    attempted_task_ids = []
    mocker.patch("apps.cmdb.services.collect_service.CollectModelService.delete_butch_node_params")

    def fail_config(task):
        attempted_task_ids.append(task.id)
        raise RuntimeError("configuration backend unavailable")

    mocker.patch(
        "apps.cmdb.services.collect_service.CollectModelService.push_butch_node_params",
        side_effect=fail_config,
    )

    assert FirstCollectionOrchestrator.recover()["scanned"] == 2
    assert FirstCollectionOrchestrator.recover()["scanned"] == 1

    assert tasks[2].id in attempted_task_ids


def test_config_recovery_stops_after_bounded_attempts(mocker):
    from apps.cmdb.models.first_collection_run import FirstCollectionRun
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator

    task = create_collect_task()
    run = FirstCollectionOrchestrator.schedule(task, reason="create")
    push = mocker.patch(
        "apps.cmdb.services.collect_service.CollectModelService.push_butch_node_params",
        side_effect=RuntimeError("configuration backend unavailable"),
    )
    mocker.patch("apps.cmdb.services.collect_service.CollectModelService.delete_butch_node_params")

    for _index in range(FirstCollectionOrchestrator.MAX_CONFIG_RECOVERY_ATTEMPTS):
        FirstCollectionRun.objects.filter(id=run.id).update(
            updated_at=timezone.now() - FirstCollectionOrchestrator.RECOVERY_STALE_AFTER,
        )
        assert FirstCollectionOrchestrator.recover()["failed"] == 1

    run.refresh_from_db()
    assert run.status == FirstCollectionRun.STATUS_FAILED
    assert run.config_attempt == FirstCollectionOrchestrator.MAX_CONFIG_RECOVERY_ATTEMPTS
    assert run.failed_stage == "config_sync"
    assert run.finished_at is not None
    assert push.call_count == FirstCollectionOrchestrator.MAX_CONFIG_RECOVERY_ATTEMPTS

    FirstCollectionRun.objects.filter(id=run.id).update(
        updated_at=timezone.now() - FirstCollectionOrchestrator.RECOVERY_STALE_AFTER,
    )
    assert FirstCollectionOrchestrator.recover()["scanned"] == 0
    assert push.call_count == FirstCollectionOrchestrator.MAX_CONFIG_RECOVERY_ATTEMPTS


def test_expired_third_attempt_converges_without_starting_a_fourth(mocker):
    from apps.cmdb.models.first_collection_run import FirstCollectionRun
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator

    task = create_collect_task()
    run = FirstCollectionOrchestrator.schedule(task, reason="create")
    FirstCollectionRun.objects.filter(id=run.id).update(
        status=FirstCollectionRun.STATUS_RUNNING,
        attempt=FirstCollectionOrchestrator.MAX_ATTEMPTS,
        claim_token="expired-claim",
        lease_expires_at=timezone.now(),
    )
    node_mgmt = mocker.patch("apps.cmdb.services.first_collection_orchestrator.NodeMgmt")

    assert FirstCollectionOrchestrator.execute(run.id) == {
        "run_id": run.id,
        "status": FirstCollectionRun.STATUS_FAILED,
    }

    run.refresh_from_db()
    assert run.attempt == FirstCollectionOrchestrator.MAX_ATTEMPTS
    assert run.claim_token == ""
    assert run.finished_at is not None
    node_mgmt.assert_not_called()


@pytest.mark.parametrize("reason", ["disabled", "ineligible", "missing"])
def test_execute_skips_run_when_task_can_no_longer_be_collected(mocker, reason):
    from apps.cmdb.models.first_collection_run import FirstCollectionRun
    from apps.cmdb.services.first_collection_orchestrator import FirstCollectionOrchestrator

    task = create_collect_task()
    run = FirstCollectionOrchestrator.schedule(task, reason="create")
    FirstCollectionRun.objects.filter(id=run.id).update(status=FirstCollectionRun.STATUS_PENDING)
    if reason == "disabled":
        mocker.patch("apps.cmdb.services.first_collection_orchestrator.cmdb_constants.CMDB_FIRST_COLLECTION_ENABLED", False)
    elif reason == "ineligible":
        task.is_interval = False
        task.save(update_fields=["is_interval"])
    else:
        task.delete()
    node_mgmt = mocker.patch("apps.cmdb.services.first_collection_orchestrator.NodeMgmt")

    assert FirstCollectionOrchestrator.execute(run.id) == {"run_id": run.id, "status": reason}

    run.refresh_from_db()
    assert run.status == FirstCollectionRun.STATUS_SKIPPED
    assert run.failed_stage == reason
    node_mgmt.assert_not_called()
