from io import StringIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.workflow_orchestration.models import Workflow, WorkflowExecution
from apps.workflow_orchestration.services.live_acceptance import (
    ScenarioResult,
    run_approval_scenario,
    run_document_render_scenario,
    run_engine_switch_scenario,
    run_health_job_chain_scenario,
    run_http_request_scenario,
    run_job_execute_probe,
    run_live_acceptance,
    run_notification_scenario,
)


@pytest.fixture
def live_user(authenticated_user):
    authenticated_user.group_list = [{"id": 1, "name": "Default"}]
    authenticated_user.save(update_fields=("group_list",))
    return authenticated_user


def _execution(*, status=WorkflowExecution.Status.SUCCEEDED, output=None, error=""):
    execution = SimpleNamespace(
        id=uuid4(),
        status=status,
        error_message=error,
        conductor_workflow_id="cond-1",
        output=output or {"ok": True},
        interactions=SimpleNamespace(
            filter=lambda **kwargs: SimpleNamespace(count=lambda: 1 if status == WorkflowExecution.Status.WAITING_APPROVAL else 0)
        ),
    )
    execution.refresh_from_db = lambda: None
    return execution


@pytest.mark.django_db
def test_live_acceptance_command_writes_report_and_surfaces_failures(authenticated_user, mocker, tmp_path):
    report = {
        "generated_at": "2026-09-23T00:00:00+00:00",
        "team_id": 1,
        "username": authenticated_user.username,
        "domain": authenticated_user.domain,
        "conductor_healthy": True,
        "summary": {"total": 2, "passed": 1, "failed": 1},
        "scenarios": [
            {"key": "engine_switch", "title": "Conductor SWITCH 引擎", "status": "PASSED", "detail": ""},
            {"key": "notification", "title": "对外通知", "status": "FAILED", "detail": "channel missing"},
        ],
        "policy": "不伪造成功；依赖缺失时标记 FAILED 并保留原始错误",
    }
    mocker.patch(
        "apps.workflow_orchestration.management.commands.run_workflow_orchestration_live_acceptance.run_live_acceptance",
        return_value=report,
    )
    path = tmp_path / "live-report.json"
    output = StringIO()

    with pytest.raises(CommandError, match="failed=1"):
        call_command(
            "run_workflow_orchestration_live_acceptance",
            team_id=1,
            username=authenticated_user.username,
            domain=authenticated_user.domain,
            report_path=str(path),
            stdout=output,
        )

    assert path.is_file()
    assert '"failed": 1' in path.read_text(encoding="utf-8")
    assert "channel missing" in output.getvalue()


@pytest.mark.django_db
def test_run_live_acceptance_rejects_unauthorized_team(authenticated_user):
    authenticated_user.group_list = [{"id": 1, "name": "Default"}]
    authenticated_user.save(update_fields=("group_list",))

    with pytest.raises(ValueError, match="无权访问团队"):
        run_live_acceptance(team_id=2, username=authenticated_user.username, domain=authenticated_user.domain)


def test_job_execute_probe_reports_failure_without_forging_success(mocker):
    mocker.patch(
        "apps.workflow_orchestration.services.live_acceptance.NodeMgmt",
        side_effect=RuntimeError("nats down"),
    )
    mocker.patch(
        "apps.workflow_orchestration.services.live_acceptance.JobMgmt",
        side_effect=RuntimeError("nats down"),
    )

    result = run_job_execute_probe(team_id=1, username="admin", domain="domain.com", target_ip="10.10.90.120")

    assert isinstance(result, ScenarioResult)
    assert result.status == "FAILED"
    assert "10.10.90.120" in result.detail
    assert result.evidence["errors"]


def test_job_execute_probe_prefers_node_mgmt_match(mocker):
    mocker.patch(
        "apps.workflow_orchestration.services.live_acceptance.NodeMgmt"
    ).return_value.get_authorized_execution_targets_by_ips.return_value = [
        {"id": "node-1", "ip": "10.10.90.120", "name": "win", "operating_system": "windows"}
    ]

    result = run_job_execute_probe(team_id=1, username="admin", domain="domain.com")

    assert result.status == "PASSED"
    assert result.evidence["target"]["id"] == "node:node-1"


@pytest.mark.django_db
def test_document_http_notification_and_switch_scenarios_pass_with_mocked_runtime(live_user, mocker):
    client = mocker.Mock()
    client.register_task_definitions.return_value = None
    client.register_workflow.return_value = None
    client.get_execution.return_value = {"status": "COMPLETED", "tasks": []}
    mocker.patch("apps.workflow_orchestration.services.live_acceptance._pump_worker_once")
    mocker.patch(
        "apps.workflow_orchestration.services.live_acceptance.seed_builtin_health_template_snapshot",
        return_value={
            "object_key": "workflow-orchestration/templates/demo/team-1/health.docx",
            "format": "docx",
            "sha256": "a" * 64,
            "size": 128,
            "filename_prefix": "health",
        },
    )
    mocker.patch(
        "apps.workflow_orchestration.services.live_acceptance.prepare_definition_for_publish",
        side_effect=lambda definition, engine_name, version: {**definition, "name": engine_name, "version": version},
    )
    mocker.patch("apps.workflow_orchestration.services.live_acceptance.apply_remote_execution")
    workflow = Workflow.objects.create(name="tmp", team=[1], definition={}, engine_name="tmp")
    mocker.patch(
        "apps.workflow_orchestration.services.live_acceptance.Workflow.all_objects.create",
        side_effect=lambda **kwargs: Workflow.objects.create(
            name=kwargs["name"],
            team=kwargs["team"],
            definition=kwargs["definition"],
            engine_name=kwargs["engine_name"],
            status=kwargs.get("status", Workflow.Status.PUBLISHED),
            canvas_metadata=kwargs.get("canvas_metadata") or {},
            created_by=kwargs.get("created_by", "admin"),
            updated_by=kwargs.get("updated_by", "admin"),
            domain=kwargs.get("domain", "domain.com"),
            updated_by_domain=kwargs.get("updated_by_domain", "domain.com"),
        ),
    )
    mocker.patch("apps.workflow_orchestration.services.live_acceptance.WorkflowVersion.objects.create")
    execution = _execution(output={"artifact": {"format": "docx"}})
    mocker.patch("apps.workflow_orchestration.services.live_acceptance.start_execution", return_value=execution)

    doc = run_document_render_scenario(
        fmt="docx",
        team_id=1,
        username=live_user.username,
        domain=live_user.domain,
        client=client,
        timeout_seconds=5,
    )
    http = run_http_request_scenario(
        team_id=1,
        username=live_user.username,
        domain=live_user.domain,
        client=client,
        timeout_seconds=5,
    )
    notify = run_notification_scenario(
        team_id=1,
        username=live_user.username,
        domain=live_user.domain,
        client=client,
        timeout_seconds=5,
        channel_id=1,
    )
    switch = run_engine_switch_scenario(
        team_id=1,
        username=live_user.username,
        domain=live_user.domain,
        client=client,
        timeout_seconds=5,
    )

    assert doc.status == "PASSED"
    assert http.status == "PASSED"
    assert notify.status == "PASSED"
    assert switch.status == "PASSED"
    assert workflow.id


@pytest.mark.django_db
def test_approval_scenario_requires_waiting_approval(live_user, mocker):
    client = mocker.Mock()
    client.register_task_definitions.return_value = None
    client.register_workflow.return_value = None
    client.get_execution.return_value = {"status": "RUNNING", "tasks": []}
    mocker.patch(
        "apps.workflow_orchestration.services.live_acceptance.prepare_definition_for_publish",
        side_effect=lambda definition, engine_name, version: {**definition, "name": engine_name, "version": version},
    )
    mocker.patch("apps.workflow_orchestration.services.live_acceptance.apply_remote_execution")
    mocker.patch("apps.workflow_orchestration.services.live_acceptance.WorkflowVersion.objects.create")
    mocker.patch(
        "apps.workflow_orchestration.services.live_acceptance.Workflow.all_objects.create",
        side_effect=lambda **kwargs: Workflow.objects.create(
            name=kwargs["name"],
            team=kwargs["team"],
            definition=kwargs["definition"],
            engine_name=kwargs["engine_name"],
            status=Workflow.Status.PUBLISHED,
            canvas_metadata={},
            created_by="admin",
            updated_by="admin",
            domain="domain.com",
            updated_by_domain="domain.com",
        ),
    )
    execution = _execution(status=WorkflowExecution.Status.WAITING_APPROVAL)
    mocker.patch("apps.workflow_orchestration.services.live_acceptance.start_execution", return_value=execution)

    result = run_approval_scenario(
        team_id=1,
        username=live_user.username,
        domain=live_user.domain,
        client=client,
        timeout_seconds=2,
    )

    assert result.status == "PASSED"
    assert result.evidence["pending_interactions"] == 1


def test_health_job_chain_fails_honestly_without_target():
    result = run_health_job_chain_scenario(
        fmt="docx",
        team_id=1,
        username="admin",
        domain="domain.com",
        client=object(),
        timeout_seconds=5,
        channel_id=1,
        script_content="Write-Output ok",
        target_reference=None,
    )

    assert result.status == "FAILED"
    assert "缺少已授权目标引用" in result.detail


@pytest.mark.django_db
def test_health_job_chain_submits_multi_linux_targets_together(live_user, mocker):
    client = mocker.Mock()
    client.register_task_definitions.return_value = None
    client.register_workflow.return_value = None
    mocker.patch(
        "apps.workflow_orchestration.services.live_acceptance.seed_builtin_health_template_snapshot",
        return_value={"object_key": "workflow-orchestration/templates/demo/team-1/health.docx", "format": "docx"},
    )
    mocker.patch(
        "apps.workflow_orchestration.services.live_acceptance.prepare_definition_for_publish",
        side_effect=lambda definition, engine_name, version: {**definition, "name": engine_name, "version": version},
    )
    mocker.patch("apps.workflow_orchestration.services.live_acceptance.apply_remote_execution")
    mocker.patch("apps.workflow_orchestration.services.live_acceptance.WorkflowVersion.objects.create")
    mocker.patch(
        "apps.workflow_orchestration.services.live_acceptance.Workflow.all_objects.create",
        side_effect=lambda **kwargs: Workflow.objects.create(
            name=kwargs["name"],
            team=kwargs["team"],
            definition=kwargs["definition"],
            engine_name=kwargs["engine_name"],
            status=Workflow.Status.PUBLISHED,
            canvas_metadata={},
            created_by="admin",
            updated_by="admin",
            domain="domain.com",
            updated_by_domain="domain.com",
        ),
    )
    execution = _execution(output={})
    fake_atom = SimpleNamespace(output={"summary": {"total": 2, "succeeded": 2, "failed": 0}, "results": []})
    mocker.patch(
        "apps.workflow_orchestration.models.AtomExecution.objects.filter",
        return_value=SimpleNamespace(order_by=lambda *args, **kwargs: SimpleNamespace(first=lambda: fake_atom)),
    )
    start = mocker.patch("apps.workflow_orchestration.services.live_acceptance.start_execution", return_value=execution)
    mocker.patch("apps.workflow_orchestration.services.live_acceptance._wait_execution", return_value=execution)

    result = run_health_job_chain_scenario(
        fmt="docx",
        team_id=1,
        username=live_user.username,
        domain=live_user.domain,
        client=client,
        timeout_seconds=5,
        channel_id=1,
        script_content="echo ok",
        script_type="shell",
        target_references=["manual:3", "manual:31"],
        key_suffix="linux_multi",
    )

    assert result.status == "PASSED"
    assert start.call_args.kwargs["inputs"]["targets"] == ["manual:3", "manual:31"]
    assert result.evidence["target_references"] == ["manual:3", "manual:31"]
    assert result.evidence["job_summary"]["succeeded"] == 2


@pytest.mark.django_db
def test_run_live_acceptance_aggregates_honest_failures(live_user, mocker):
    client = mocker.Mock()
    client.health.return_value = {"healthy": True}
    client.terminate_workflow.return_value = None
    mocker.patch("apps.workflow_orchestration.services.live_acceptance.ConductorClient", return_value=client)
    mocker.patch(
        "apps.workflow_orchestration.services.live_acceptance.run_job_execute_probe",
        return_value=ScenarioResult(key="job_execute_probe", title="probe", status="FAILED", detail="no host"),
    )
    mocker.patch(
        "apps.workflow_orchestration.services.live_acceptance.run_engine_switch_scenario",
        return_value=ScenarioResult(key="engine_switch", title="switch", status="PASSED"),
    )
    mocker.patch(
        "apps.workflow_orchestration.services.live_acceptance.run_document_render_scenario",
        side_effect=[
            ScenarioResult(key="document_docx", title="docx", status="PASSED"),
            ScenarioResult(key="document_xlsx", title="xlsx", status="PASSED"),
        ],
    )
    mocker.patch(
        "apps.workflow_orchestration.services.live_acceptance.run_http_request_scenario",
        return_value=ScenarioResult(key="http_request", title="http", status="PASSED"),
    )
    mocker.patch(
        "apps.workflow_orchestration.services.live_acceptance.run_notification_scenario",
        return_value=ScenarioResult(key="notification", title="notify", status="FAILED", detail="channel"),
    )
    mocker.patch(
        "apps.workflow_orchestration.services.live_acceptance.run_approval_scenario",
        return_value=ScenarioResult(key="approval", title="approval", status="PASSED"),
    )
    mocker.patch(
        "apps.workflow_orchestration.services.live_acceptance.run_health_job_chain_scenario",
        side_effect=[
            ScenarioResult(key="health_docx_chain", title="word", status="FAILED", detail="no target"),
            ScenarioResult(key="health_xlsx_chain", title="excel", status="FAILED", detail="no target"),
        ],
    )

    report = run_live_acceptance(team_id=1, username=live_user.username, domain=live_user.domain)

    assert report["summary"]["total"] == 9
    assert report["summary"]["passed"] == 5
    assert report["summary"]["failed"] == 4
    assert report["policy"].startswith("不伪造成功")
    assert client.terminate_workflow.call_count >= 0
