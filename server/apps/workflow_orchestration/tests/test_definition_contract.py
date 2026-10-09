import copy

import pytest

from apps.workflow_orchestration.services.atoms import TASK_DEFINITIONS
from apps.workflow_orchestration.services.definitions import (
    DefinitionValidationError,
    build_health_inspection_canvas_metadata,
    build_health_inspection_definition,
    escape_conductor_literal_text,
    prepare_definition_for_publish,
    validate_conductor_definition,
)


def test_health_starter_is_native_conductor_definition():
    definition = build_health_inspection_definition()

    assert "apiVersion" not in definition
    assert "spec" not in definition
    assert definition["schemaVersion"] == 2
    assert [task["type"] for task in definition["tasks"]] == ["SIMPLE", "SIMPLE", "SIMPLE"]
    assert definition["tasks"][-1]["name"] == "bklite_notification"


def test_health_starter_ends_at_report_without_form_return():
    metadata = build_health_inspection_canvas_metadata()

    assert metadata["return_nodes"] == []
    assert metadata["edges"] == [
        {"id": "trigger-scan", "source": "trigger_form", "target": "scan"},
        {"id": "scan-report", "source": "scan", "target": "report"},
        {"id": "report-notify", "source": "report", "target": "notify"},
    ]
    fields = metadata["trigger_nodes"][0]["input_schema"]["properties"]
    assert fields["targets"]["x-widget"] == "target-selector"
    assert "report_template" not in fields
    assert "rules" not in fields


def test_escape_conductor_literal_text_doubles_bare_dollar_braces():
    assert escape_conductor_literal_text("x=${collected_at}y") == "x=$${collected_at}y"
    assert escape_conductor_literal_text("already=$${ok}") == "already=$${ok}"
    assert escape_conductor_literal_text("no braces $var") == "no braces $var"


def test_prepare_definition_escapes_script_content_literals_for_conductor():
    definition = build_health_inspection_definition()
    definition["tasks"][0]["inputParameters"]["script_content"] = 'echo "${HOME}"'
    published = prepare_definition_for_publish(definition, engine_name="escape_demo", version=1)
    assert published["tasks"][0]["inputParameters"]["script_content"] == 'echo "$${HOME}"'
    # workflow references must stay single-dollar
    assert published["tasks"][0]["inputParameters"]["targets"] == "${workflow.input.targets}"


def test_linux_health_script_avoids_conductor_expression_braces():
    from apps.workflow_orchestration.management.commands.seed_workflow_orchestration_demo import LINUX_HEALTH_SCRIPT

    assert "${" not in LINUX_HEALTH_SCRIPT


def test_publish_freezes_engine_identity_without_mutating_draft():
    draft = build_health_inspection_definition()
    draft["tasks"][0]["inputParameters"]["script_content"] = "Write-Output ok"
    original = copy.deepcopy(draft)

    published = prepare_definition_for_publish(
        draft,
        engine_name="bklite_workflow_42",
        version=3,
    )

    assert draft == original
    assert published["name"] == "bklite_workflow_42"
    assert published["version"] == 3


def test_unknown_simple_atom_is_rejected():
    definition = build_health_inspection_definition()
    definition["tasks"][0]["name"] = "unknown_atom"

    with pytest.raises(DefinitionValidationError, match="unknown_atom"):
        prepare_definition_for_publish(definition, engine_name="wf", version=1)


def test_job_scan_tasks_do_not_retry_non_idempotent_submission():
    definitions = {definition["name"]: definition for definition in TASK_DEFINITIONS}

    assert definitions["bklite_job_execute"]["retryCount"] == 0
    assert definitions["bklite_job_execute"]["responseTimeoutSeconds"] > 3600
    assert "bklite_inspection_scan" not in definitions
    assert "bklite_inspection_scan_linux" not in definitions
    assert "bklite_inspection_scan_windows" not in definitions

    workflow_definition = build_health_inspection_definition()
    scan = workflow_definition["tasks"][0]
    assert scan["name"] == "bklite_job_execute"
    assert scan["inputParameters"]["targets"] == "${workflow.input.targets}"
    assert scan["inputParameters"]["actor"] == "${workflow.input.actor}"
    assert scan["inputParameters"]["script_type"] == "shell"
    assert scan["inputParameters"]["script_content"] == ""
    assert scan["inputParameters"]["execution_params"] == ""
    assert scan["inputParameters"]["timeout_seconds"] == 600
    assert "linux_script_content" not in scan["inputParameters"]
    assert "windows_script_content" not in scan["inputParameters"]
    assert "failure_policy" not in scan["inputParameters"]


def test_health_starter_is_composed_from_configurable_general_atoms():
    definition = build_health_inspection_definition()
    tasks = definition["tasks"]

    scan = tasks[0]
    assert scan["name"] == "bklite_job_execute"
    assert scan["inputParameters"]["targets"] == "${workflow.input.targets}"
    assert scan["inputParameters"]["script_content"] == ""
    assert "failure_policy" not in scan["inputParameters"]
    assert "variant" not in scan["inputParameters"]

    report = tasks[1]
    assert report["name"] == "bklite_document_render"
    assert "template" not in report["inputParameters"]
    assert report["inputParameters"]["data"] == "${scan.output}"
    notify = tasks[2]
    assert notify["name"] == "bklite_notification"
    assert notify["inputParameters"]["report_artifact"] == "${report.output.artifact}"


def test_general_control_flow_and_approval_definition_is_accepted():
    definition = {
        "name": "change_with_approval",
        "version": 1,
        "schemaVersion": 2,
        "inputParameters": ["environment"],
        "tasks": [
            {
                "name": "approval",
                "taskReferenceName": "approval",
                "type": "HUMAN",
                "inputParameters": {
                    "interactionType": "APPROVAL",
                    "title": "确认执行",
                    "candidates": ["alice"],
                    "publicContext": {"environment": "${workflow.input.environment}"},
                },
            },
            {
                "name": "approval_branch",
                "taskReferenceName": "approval_branch",
                "type": "SWITCH",
                "inputParameters": {"decision": "${approval.output.approved}"},
                "evaluatorType": "value-param",
                "expression": "decision",
                "decisionCases": {
                    "true": [
                        {
                            "name": "bklite_notification",
                            "taskReferenceName": "notify_approved",
                            "type": "SIMPLE",
                            "inputParameters": {"notification_type": "EMAIL", "channel_id": 1, "recipients": ["alice"], "title": "通过", "body": "已通过"},
                        }
                    ],
                    "false": [
                        {
                            "name": "bklite_notification",
                            "taskReferenceName": "notify_rejected",
                            "type": "SIMPLE",
                            "inputParameters": {"notification_type": "EMAIL", "channel_id": 1, "recipients": ["alice"], "title": "驳回", "body": "已驳回"},
                        }
                    ],
                },
            },
        ],
    }

    published = prepare_definition_for_publish(definition, engine_name="wf", version=1)

    assert published["tasks"][0]["type"] == "HUMAN"


def test_structured_condition_switch_is_accepted():
    definition = {
        "tasks": [
            {
                "name": "condition",
                "taskReferenceName": "condition_1",
                "type": "SWITCH",
                "inputParameters": {
                    "left_0": "${workflow.input.cpu}",
                    "right_0": 80,
                    "left_1": "${workflow.input.region}",
                    "right_1": "${workflow.input.expected_region}",
                },
                "evaluatorType": "javascript",
                "expression": "($.left_0 >= $.right_0 && $.left_1 == $.right_1) ? 'true' : 'false'",
                "decisionCases": {"true": [], "false": []},
                "defaultCase": [],
            }
        ]
    }

    assert validate_conductor_definition(definition)["tasks"][0]["name"] == "condition"


@pytest.mark.parametrize(
    "expression",
    [
        "($.left_0.indexOf($.right_0) < 0) ? 'true' : 'false'",
        "($.left_0.indexOf($.right_0) == 0) ? 'true' : 'false'",
        "($.left_0.slice($.left_0.length - $.right_0.length) == $.right_0) ? 'true' : 'false'",
    ],
)
def test_structured_condition_supports_migrated_string_operators(expression):
    definition = {
        "tasks": [
            {
                "name": "condition",
                "taskReferenceName": "condition_1",
                "type": "SWITCH",
                "inputParameters": {"left_0": "${workflow.input.message}", "right_0": "error"},
                "evaluatorType": "javascript",
                "expression": expression,
                "decisionCases": {"true": [], "false": []},
                "defaultCase": [],
            }
        ]
    }

    assert validate_conductor_definition(definition)["tasks"][0]["expression"] == expression


def test_condition_rejects_free_javascript_expression():
    definition = {
        "tasks": [
            {
                "name": "condition",
                "taskReferenceName": "condition_1",
                "type": "SWITCH",
                "inputParameters": {"left_0": "${workflow.input.cpu}", "right_0": 80},
                "evaluatorType": "javascript",
                "expression": "process.exit(1)",
                "decisionCases": {"true": [], "false": []},
            }
        ]
    }

    with pytest.raises(DefinitionValidationError, match="结构化条件"):
        validate_conductor_definition(definition)


def test_control_nesting_deeper_than_five_is_rejected():
    nested = [
        {
            "name": "bklite_notification",
            "taskReferenceName": "leaf",
            "type": "SIMPLE",
            "inputParameters": {
                "notification_type": "EMAIL",
                "channel_id": 1,
                "body": "leaf",
            },
        }
    ]
    for depth in range(6, 0, -1):
        nested = [
            {
                "name": f"router_{depth}",
                "taskReferenceName": f"router_{depth}",
                "type": "SWITCH",
                "decisionCases": {"true": nested},
            }
        ]

    with pytest.raises(DefinitionValidationError, match="嵌套深度"):
        validate_conductor_definition({"tasks": nested})


def test_approval_without_candidates_is_rejected():
    definition = {
        "tasks": [
            {
                "name": "approval",
                "taskReferenceName": "approval",
                "type": "HUMAN",
                "inputParameters": {"title": "确认"},
            }
        ]
    }

    with pytest.raises(DefinitionValidationError, match="候选审批人"):
        prepare_definition_for_publish(definition, engine_name="wf", version=1)


def test_approval_without_fixed_decision_branches_is_rejected():
    definition = {
        "tasks": [
            {
                "name": "approval",
                "taskReferenceName": "approval",
                "type": "HUMAN",
                "inputParameters": {"title": "确认", "candidates": ["alice"]},
            }
        ]
    }

    with pytest.raises(DefinitionValidationError, match="true/false"):
        prepare_definition_for_publish(definition, engine_name="wf", version=1)


@pytest.mark.parametrize("task_type", ["DO_WHILE", "WAIT"])
def test_non_mvp_loop_and_wait_nodes_are_rejected(task_type):
    definition = {
        "tasks": [
            {
                "name": "unsupported",
                "taskReferenceName": "unsupported",
                "type": task_type,
                "loopCondition": "if ($.loop.iteration < 10) { true } else { false }",
                "loopOver": [
                    {
                        "name": "bklite_notification",
                        "taskReferenceName": "inside",
                        "type": "SIMPLE",
                        "inputParameters": {
                            "notification_type": "EMAIL",
                            "channel_id": 1,
                            "body": "inside",
                        },
                    }
                ],
            }
        ]
    }

    with pytest.raises(DefinitionValidationError, match="不支持的 Conductor 节点类型"):
        prepare_definition_for_publish(definition, engine_name="wf", version=1)


def test_atom_required_inputs_are_enforced_before_publish():
    definition = {
        "tasks": [
            {
                "name": "bklite_notification",
                "taskReferenceName": "notify",
                "type": "SIMPLE",
                "inputParameters": {
                    "channel_id": 1,
                    "recipients": ["ops@example.com"],
                    "title": "巡检完成",
                },
            }
        ]
    }

    with pytest.raises(DefinitionValidationError, match="notify.*body"):
        prepare_definition_for_publish(definition, engine_name="wf", version=1)


def test_atom_literal_inputs_follow_schema_but_conductor_references_remain_allowed():
    invalid = {
        "tasks": [
            {
                "name": "bklite_notification",
                "taskReferenceName": "notify",
                "type": "SIMPLE",
                "inputParameters": {
                    "notification_type": "EMAIL",
                    "channel_id": "not-an-integer",
                    "recipients": ["ops@example.com"],
                    "title": "巡检完成",
                    "body": "正文",
                },
            }
        ]
    }
    dynamic = copy.deepcopy(invalid)
    dynamic["tasks"][0]["inputParameters"]["channel_id"] = "${workflow.input.channel_id}"

    with pytest.raises(DefinitionValidationError, match="notify.*channel_id"):
        prepare_definition_for_publish(invalid, engine_name="wf", version=1)
    assert prepare_definition_for_publish(dynamic, engine_name="wf", version=1)["tasks"][0]["name"] == "bklite_notification"
