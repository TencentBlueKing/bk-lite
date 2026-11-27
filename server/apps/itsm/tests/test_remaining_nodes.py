"""长流程验收发现的发布与节点执行回归。"""
import json
from unittest.mock import patch
from xml.etree import ElementTree as ET

import pytest

from apps.itsm.flowable.bpmn_builder import BPMN, build_bpmn
from apps.itsm.models import Workflow, WorkflowVersion
from apps.itsm.tests.test_review_regressions import request
from apps.itsm.views.api import publish_workflow


def design(kind, auto=None):
    return {
        "nodes": [
            {"id": "s", "type": "start"},
            {"id": "n", "type": kind, "name": "待验证节点", "auto": auto or {}, "fallback": "admin"},
            {"id": "e", "type": "end"},
        ],
        "edges": [{"from": "s", "to": "n"}, {"from": "n", "to": "e", "default": True}],
    }


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["subprocess", "subprocess_submit", "call"])
@pytest.mark.parametrize("state", ["missing", "draft", "other_domain", "published"])
def test_publish_requires_local_published_child(kind, state):
    parent = Workflow.objects.create(key="parent", name="父流程")
    version = WorkflowVersion.objects.create(workflow=parent, version_no=1, design=design(kind, {"process_key": "child"}))
    if state != "missing":
        child = Workflow.objects.create(key="child", name="子流程", domain="other.com" if state == "other_domain" else "domain.com")
        cv = WorkflowVersion.objects.create(
            workflow=child,
            version_no=1,
            is_published=state != "draft",
            flowable_deployment_id="deployed" if state != "draft" else "",
            process_definition_key="child",
        )
        child.current_version = cv
        child.save()
    with patch("apps.itsm.views.api.FlowableClient") as client:
        client.return_value.definition_for_deployment.return_value = "tested:1:stable"
        client.return_value.deploy_bpmn.return_value = {"id": "parent-deployment"}
        body = json.loads(publish_workflow(request("post", permissions=["workflow-Publish"]), parent.id).content)
        assert body["result"] is (state == "published")
        assert client.return_value.deploy_bpmn.called is (state == "published")
    version.refresh_from_db()
    assert version.is_published is (state == "published")


def test_conditional_parallel_uses_inclusive_gateway():
    root = ET.fromstring(build_bpmn(design("parallel_condition")))
    assert root.find(f".//{{{BPMN}}}inclusiveGateway") is not None


def test_manual_trigger_waits_before_external_action():
    root = ET.fromstring(build_bpmn(design("manual_trigger", {"kind": "table", "table_key": "demo"})))
    assert root.find(f'.//{{{BPMN}}}userTask[@id="n"]') is not None
    assert root.find(f'.//{{{BPMN}}}serviceTask[@id="n__action"]') is not None


@pytest.mark.parametrize("amount,expected", [(100, False), (1500, True)])
def test_rule_trigger_only_executes_when_matched(amount, expected):
    from types import SimpleNamespace

    from apps.itsm.services.external_jobs import execute_node

    with patch("apps.itsm.services.external_jobs.run_auto_action", return_value=("done", {"ok": True})) as run:
        result = execute_node(
            SimpleNamespace(form_data={"amount": amount}),
            {"type": "rule_trigger", "auto": {"kind": "table", "table_key": "demo", "when": {"field": "amount", "op": ">=", "value": 1000}}},
        )
        assert run.called is expected
        assert result == ({"ok": True} if expected else {"skipped": True, "reason": "未满足触发条件"})


@pytest.mark.parametrize("kind", ["subprocess", "subprocess_submit", "call"])
@pytest.mark.django_db
def test_empty_or_self_subprocess_cannot_publish(kind):
    from apps.itsm.services.workflow.dependencies import validate_subprocesses

    workflow = Workflow.objects.create(key="self", name="自己")
    for key in ["", "self"]:
        with pytest.raises(ValueError, match="子流程未发布或不可用"):
            validate_subprocesses(design(kind, {"process_key": key}), workflow)


@pytest.mark.parametrize("kind", ["manual_trigger", "rule_trigger"])
def test_trigger_requires_action_configuration(kind):
    from apps.itsm.flowable.validator import validate_design

    assert any("执行动作" in error for error in validate_design(design(kind)))


def test_auto_node_rejects_retired_action_at_publish():
    from apps.itsm.flowable.validator import validate_design

    assert any("执行动作已停用" in error for error in validate_design(design("auto", {"kind": "retired_action"})))
    assert not validate_design(design("auto", {"kind": "job_template"}))


@pytest.mark.django_db
def test_manual_trigger_job_retries_do_not_repeat_action():
    from unittest.mock import Mock

    from apps.itsm.models import DataTable, DataTableRow, Ticket
    from apps.itsm.services.external_jobs import process_job

    table = DataTable.objects.create(key="manual_result", name="手动触发结果")
    workflow = Workflow.objects.create(key="manual_test", name="手动触发")
    version = WorkflowVersion.objects.create(
        workflow=workflow,
        version_no=1,
        design=design("manual_trigger", {"kind": "table", "table_key": table.key}),
    )
    ticket = Ticket.objects.create(
        sn="manual-repeat", title="确认后执行", workflow=workflow, workflow_version=version, creator="admin", process_instance_id="p"
    )
    job = {"id": "job", "elementId": "n__action", "processInstanceId": "p"}
    client = Mock()
    with patch("apps.itsm.services.external_jobs.TicketService"):
        assert process_job(client, job)
        assert process_job(client, job)
    assert DataTableRow.objects.filter(table=table).count() == 1
    client.complete_external_job.assert_called_once()
    assert ticket.auto_executions.get().status == "done"


def test_subprocess_key_trim_matches_publish_validation():
    root = ET.fromstring(build_bpmn(design("subprocess_submit", {"process_key": " child "})))
    assert root.find(f".//{{{BPMN}}}callActivity").get("calledElement") == "child"
