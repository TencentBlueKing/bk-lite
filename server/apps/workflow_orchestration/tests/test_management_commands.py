from io import StringIO

from django.core.management import call_command


def test_trigger_scheduler_once_runs_all_runtime_reconciliation_steps(mocker):
    run_cron = mocker.patch(
        "apps.workflow_orchestration.management.commands.run_workflow_trigger_scheduler.run_due_cron_triggers",
        return_value={"succeeded": 1, "skipped": 0, "failed": 0},
    )
    expire = mocker.patch(
        "apps.workflow_orchestration.management.commands.run_workflow_trigger_scheduler.expire_due_interactions",
        return_value={"timed_out": 1, "failed": 0},
    )
    retry = mocker.patch(
        "apps.workflow_orchestration.management.commands.run_workflow_trigger_scheduler.retry_pending_interaction_deliveries",
        return_value={"delivered": 1, "failed": 0},
    )
    sync = mocker.patch(
        "apps.workflow_orchestration.management.commands.run_workflow_trigger_scheduler.sync_active_executions",
        return_value={"synchronized": 1, "failed": 0},
    )
    output = StringIO()

    call_command("run_workflow_trigger_scheduler", once=True, interval=1, stdout=output)

    run_cron.assert_called_once_with()
    expire.assert_called_once_with()
    retry.assert_called_once_with()
    sync.assert_called_once_with()
    assert "cron triggers: succeeded=1" in output.getvalue()
    assert "execution sync: synchronized=1" in output.getvalue()


def test_artifact_cleanup_scheduler_once_honors_batch_size_and_reports_result(mocker):
    cleanup = mocker.patch(
        "apps.workflow_orchestration.management.commands.run_workflow_artifact_cleanup_scheduler.cleanup_expired_artifacts",
        return_value={"selected": 2, "deleted": 1, "failed": 1},
    )
    output = StringIO()

    call_command("run_workflow_artifact_cleanup_scheduler", once=True, interval=1, batch_size=25, stdout=output)

    cleanup.assert_called_once_with(batch_size=25)
    assert "artifact cleanup: selected=2 deleted=1 failed=1" in output.getvalue()


def test_manual_artifact_cleanup_command_reports_auditable_summary(mocker):
    cleanup = mocker.patch(
        "apps.workflow_orchestration.management.commands.cleanup_workflow_artifacts.cleanup_expired_artifacts",
        return_value={"selected": 3, "deleted": 3, "failed": 0},
    )
    output = StringIO()

    call_command("cleanup_workflow_artifacts", batch_size=10, stdout=output)

    cleanup.assert_called_once_with(batch_size=10)
    assert "selected=3 deleted=3 failed=0" in output.getvalue()
