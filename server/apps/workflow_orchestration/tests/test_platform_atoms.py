import pytest

from apps.workflow_orchestration.models import AtomDefinition
from apps.workflow_orchestration.services.atoms import execute_atom, http_atom, notification_atom


@pytest.mark.django_db
def test_http_atom_uses_worker_trusted_context_without_ui_team_binding(mocker):
    response = mocker.Mock()
    response.status_code = 200
    response.headers = {"Content-Type": "application/json", "Content-Length": "2"}
    response.iter_content.return_value = [b"{}"]
    response.close.return_value = None
    mocker.patch(
        "apps.workflow_orchestration.atom_packages.http_runtime.safe_request",
        return_value=response,
    )
    mocker.patch(
        "apps.workflow_orchestration.atom_packages.http_runtime.SSRFValidator.validate",
        side_effect=lambda url: url,
    )

    result = http_atom(
        {
            "url": "https://api.example.com/v1/health",
            "method": "GET",
            "timeout": 5,
            "__bklite_context": {
                "execution_id": "exec-ui-1",
                "organization_id": 7,
                "actor": {"username": "alice", "domain": "example.com"},
            },
        }
    )

    assert result["status_code"] == 200


@pytest.mark.django_db
def test_notification_atom_uses_worker_trusted_context_without_ui_execution_bindings(mocker):
    from apps.system_mgmt.models import User

    User.objects.create(
        username="alice",
        display_name="Alice",
        email="alice@example.com",
        password="x",
        group_list=[{"id": 7, "name": "Current"}],
    )
    system = mocker.patch("apps.workflow_orchestration.atom_packages.bklite_notification.runtime.handler.SystemMgmt").return_value
    system.dispatch_notification.return_value = {
        "result": True,
        "code": "delivered",
        "message": "success",
        "delivery_id": "delivery-ui-1",
    }

    notified = notification_atom(
        {
            "channel_id": 3,
            "recipients": ["alice"],
            "title": "发布通知",
            "body": "已完成",
            "__bklite_context": {
                "execution_id": "exec-ui-2",
                "organization_id": 7,
                "actor": {"username": "alice", "domain": "example.com"},
            },
        }
    )

    assert notified["delivery"]["result"] is True
    assert system.dispatch_notification.call_args.kwargs["organization_ids"] == [7]
    assert system.dispatch_notification.call_args.kwargs["event_payload"]["execution_id"] == "exec-ui-2"


@pytest.mark.django_db
def test_http_atom_uses_safe_request_and_caps_response(mocker):
    response = mocker.Mock()
    response.status_code = 200
    response.headers = {"Content-Type": "application/json", "Content-Length": "18"}
    response.iter_content.return_value = [b'{"result":"ok"}']
    response.close.return_value = None
    safe_request = mocker.patch(
        "apps.workflow_orchestration.atom_packages.http_runtime.safe_request",
        return_value=response,
    )
    mocker.patch(
        "apps.workflow_orchestration.atom_packages.http_runtime.SSRFValidator.validate",
        side_effect=lambda url: url,
    )

    result = http_atom(
        {
            "team": 7,
            "actor": {"username": "atom-admin", "domain": "example.com"},
            "url": "https://api.example.com/v1/health",
            "method": "GET",
            "headers": {"Authorization": "Bearer token", "X-Trace": "trace-1"},
            "timeout": 5,
        }
    )

    assert result["status_code"] == 200
    assert result["body"] == {"result": "ok"}
    assert safe_request.call_args.args == ("GET", "https://api.example.com/v1/health")
    assert safe_request.call_args.kwargs["headers"] == {"Authorization": "Bearer token", "X-Trace": "trace-1"}

    response.iter_content.return_value = [b'{"patched":true}']
    patched = http_atom(
        {
            "team": 7,
            "url": "https://api.example.com/v1/items/1",
            "method": "PATCH",
            "body": {"status": "open"},
            "timeout": 5,
        }
    )
    assert patched["status_code"] == 200
    assert safe_request.call_args.args == ("PATCH", "https://api.example.com/v1/items/1")

    with pytest.raises(ValueError, match="HTTP URL"):
        http_atom({"team": 7, "method": "GET"})
    with pytest.raises(ValueError, match="Host"):
        http_atom(
            {
                "team": 7,
                "url": "https://api.example.com/v1/health",
                "headers": {"Host": "evil.example"},
            }
        )


@pytest.mark.django_db
def test_http_atom_enforces_ssrf_and_explicit_success_statuses(mocker):
    mocker.patch(
        "apps.workflow_orchestration.atom_packages.http_runtime.SSRFValidator.validate",
        side_effect=lambda url: url,
    )
    response = mocker.Mock(status_code=409, headers={"Content-Type": "application/json"})
    response.iter_content.return_value = [b'{"ticket_id":123}']
    mocker.patch(
        "apps.workflow_orchestration.atom_packages.http_runtime.safe_request",
        return_value=response,
    )

    with pytest.raises(ValueError, match="状态码 409"):
        http_atom(
            {
                "team": 7,
                "url": "https://tickets.example.com/api/v1/tickets/123",
                "method": "GET",
            }
        )

    response.iter_content.return_value = [b'{"ticket_id":123}']
    accepted = http_atom(
        {
            "team": 7,
            "url": "https://tickets.example.com/api/v1/tickets/123",
            "method": "GET",
            "success_status_codes": [200, 409],
            "response_format": "JSON",
        }
    )
    assert accepted["status_code"] == 409
    assert accepted["body"] == {"ticket_id": 123}

    from apps.core.utils.ssrf_validator import SSRFError

    mocker.patch(
        "apps.workflow_orchestration.atom_packages.http_runtime.SSRFValidator.validate",
        side_effect=SSRFError("blocked"),
    )
    with pytest.raises(ValueError, match="blocked"):
        http_atom(
            {
                "team": 7,
                "url": "http://127.0.0.1/admin",
                "method": "GET",
            }
        )


@pytest.mark.django_db
def test_notification_atom_uses_fixed_platform_interface(mocker):
    from apps.system_mgmt.models import User

    alice = User.objects.create(
        username="alice",
        display_name="Alice",
        email="alice@example.com",
        password="x",
        group_list=[{"id": 7, "name": "Current"}],
    )
    system = mocker.patch("apps.workflow_orchestration.atom_packages.bklite_notification.runtime.handler.SystemMgmt").return_value
    system.dispatch_notification.return_value = {"result": True, "code": "delivered", "message": "success", "delivery_id": "delivery-1"}
    notified = notification_atom(
        {
            "team": 7,
            "execution_id": "execution-1",
            "channel_id": 3,
            "recipients": ["alice"],
            "title": "发布通知",
            "body": "已完成",
        }
    )
    assert notified["delivery"]["result"] is True
    assert system.dispatch_notification.call_args.kwargs["producer"] == "workflow-orchestration"
    assert system.dispatch_notification.call_args.kwargs["recipients"] == [str(alice.id)]
    assert "report_link" not in system.dispatch_notification.call_args.kwargs["body"]


@pytest.mark.django_db
def test_notification_atom_fails_when_the_channel_rejects_delivery(mocker):
    system = mocker.patch("apps.workflow_orchestration.atom_packages.bklite_notification.runtime.handler.SystemMgmt").return_value
    system.dispatch_notification.return_value = {
        "result": False,
        "code": "invalid_recipients",
        "message": "通知接收人不符合渠道能力。",
        "retryable": False,
    }

    with pytest.raises(ValueError, match="通知接收人不符合渠道能力"):
        notification_atom(
            {
                "team": 7,
                "execution_id": "execution-1",
                "channel_id": 2,
                "recipients": ["999"],
                "title": "主机健康巡检报告",
                "body": "主机健康巡检已完成。",
            }
        )


@pytest.mark.django_db
def test_notification_atom_sends_expiring_report_link_instead_of_the_file(mocker):
    from datetime import timedelta

    from django.utils import timezone

    from apps.system_mgmt.models import User
    from apps.workflow_orchestration.models import ExecutionArtifact, Workflow, WorkflowExecution

    User.objects.create(
        username="alice",
        display_name="Alice",
        email="alice@example.com",
        password="x",
        group_list=[{"id": 7, "name": "Current"}],
    )
    system = mocker.patch("apps.workflow_orchestration.atom_packages.bklite_notification.runtime.handler.SystemMgmt").return_value
    system.dispatch_notification.return_value = {"result": True, "code": "delivered", "message": "success"}
    workflow = Workflow.objects.create(name="巡检", team=[7], definition={})
    execution = WorkflowExecution.objects.create(workflow=workflow, workflow_version=1, team=[7])
    artifact = ExecutionArtifact.objects.create(
        execution=execution,
        team=[7],
        format="docx",
        object_key="reports/a.docx",
        filename="a.docx",
        content_type="application/docx",
        sha256="c" * 64,
        size=4,
        expires_at=timezone.now() + timedelta(days=1),
    )

    notification_atom(
        {
            "team": 7,
            "execution_id": str(execution.id),
            "channel_id": 3,
            "recipients": ["alice"],
            "title": "巡检报告",
            "body": "已完成",
            "report_artifact": {"id": str(artifact.id)},
        }
    )

    body = system.dispatch_notification.call_args.kwargs["body"]
    payload = system.dispatch_notification.call_args.kwargs["event_payload"]
    assert "报告下载（24 小时内有效）" in body
    assert "artifacts/shared/?token=" in body
    assert artifact.object_key not in body
    assert payload["report_link"] == body.split("：", 1)[1]


@pytest.mark.django_db
def test_http_package_uses_its_own_fixed_url_contract(mocker):
    atom = AtomDefinition.objects.create(
        key="custom.status",
        name="状态查询",
        category="集成",
        driver="HTTP",
        built_in=False,
        source_type=AtomDefinition.SourceType.PACKAGE,
        team=[7],
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )
    atom.execution_config = {"http": {"url": "https://status.example.com/v1/health", "method": "GET"}}
    atom.save(update_fields=("execution_config", "updated_at"))
    response = mocker.Mock(
        status_code=200,
        headers={"Content-Type": "application/json"},
    )
    response.iter_content.return_value = [b'{"ok":true}']
    safe_request = mocker.patch(
        "apps.workflow_orchestration.atom_packages.http_runtime.safe_request",
        return_value=response,
    )
    mocker.patch(
        "apps.workflow_orchestration.atom_packages.http_runtime.SSRFValidator.validate",
        side_effect=lambda url: url,
    )

    result = execute_atom(
        atom.key,
        {"team": 7, "url": "https://attacker.invalid"},
    )

    assert result["body"] == {"ok": True}
    assert safe_request.call_args.args == ("GET", "https://status.example.com/v1/health")
