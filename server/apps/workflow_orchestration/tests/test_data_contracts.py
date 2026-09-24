import pytest

from apps.workflow_orchestration.models import Workflow, WorkflowVersion
from apps.workflow_orchestration.services.data_contracts import (
    redact_sensitive_inputs,
    resolve_secret_envelopes,
    validate_and_compile_workflow_data_contract,
)
from apps.workflow_orchestration.services.definitions import DefinitionValidationError, validate_workflow_inputs
from apps.workflow_orchestration.services.runtime import start_execution

CATALOG = {
    "source": {
        "input_schema": {"type": "object", "properties": {}},
        "output_schema": {
            "type": "object",
            "properties": {"count": {"type": "integer"}, "token": {"type": "string", "sensitive": True}},
        },
    },
    "sink": {
        "input_schema": {
            "type": "object",
            "properties": {
                "value": {"type": "number"},
                "label": {"type": "string"},
                "secret": {"type": "string", "secretCompatible": True},
            },
        },
        "output_schema": {"type": "object", "properties": {"result": {"type": "number"}}},
    },
}


def contract():
    return {
        "version": 1,
        "systemContextVersion": 1,
        "inputs": [
            {
                "parameterId": "input:service",
                "key": "service",
                "name": "服务",
                "schema": {"type": "string"},
                "required": True,
                "group": "basic",
                "order": 0,
                "sensitive": False,
            },
            {
                "parameterId": "input:api_token",
                "key": "api_token",
                "name": "Token",
                "schema": {"type": "string"},
                "required": True,
                "group": "advanced",
                "order": 1,
                "sensitive": True,
            },
        ],
        "constants": [],
        "outputs": [],
    }


def definition(sink_inputs):
    return {
        "tasks": [
            {"name": "source", "taskReferenceName": "source_1", "type": "SIMPLE", "inputParameters": {}},
            {"name": "sink", "taskReferenceName": "sink_1", "type": "SIMPLE", "inputParameters": sink_inputs},
        ]
    }


def test_compiles_trigger_input_index_and_accepts_integer_to_number_reference():
    data_contract = contract()
    compiled, metadata = validate_and_compile_workflow_data_contract(
        definition({"value": "${source_1.output.count}", "label": "${system.execution_id}"}),
        {"data_contract": data_contract},
        atom_catalog=CATALOG,
        strict=True,
    )

    assert metadata["input_schema"]["required"] == ["service", "api_token"]
    assert compiled["variables"] == {}
    assert compiled["outputParameters"] == {}
    assert compiled["tasks"][1]["inputParameters"]["label"] == "${workflow.input.__system.execution_id}"


def test_draft_keeps_broken_reference_but_strict_validation_blocks_it():
    broken = definition({"value": "${missing.output.value}"})
    validate_and_compile_workflow_data_contract(broken, {"data_contract": contract()}, atom_catalog=CATALOG, strict=False)

    with pytest.raises(DefinitionValidationError, match="数据引用不存在"):
        validate_and_compile_workflow_data_contract(broken, {"data_contract": contract()}, atom_catalog=CATALOG, strict=True)


def test_branch_output_is_not_available_after_branch_controller():
    candidate = {
        "tasks": [
            {
                "name": "switch",
                "taskReferenceName": "switch_1",
                "type": "SWITCH",
                "decisionCases": {"yes": [{"name": "source", "taskReferenceName": "branch_source", "type": "SIMPLE", "inputParameters": {}}]},
            },
            {"name": "sink", "taskReferenceName": "sink_1", "type": "SIMPLE", "inputParameters": {"value": "${branch_source.output.count}"}},
        ]
    }
    with pytest.raises(DefinitionValidationError, match="当前路径不保证可用"):
        validate_and_compile_workflow_data_contract(candidate, {"data_contract": contract()}, atom_catalog=CATALOG, strict=True)


def test_condition_references_and_operator_types_are_validated():
    candidate = {
        "tasks": [
            {"name": "source", "taskReferenceName": "source_1", "type": "SIMPLE", "inputParameters": {}},
            {
                "name": "condition",
                "taskReferenceName": "condition_1",
                "type": "SWITCH",
                "inputParameters": {"left_0": "${source_1.output.count}", "right_0": 80},
                "evaluatorType": "javascript",
                "expression": "($.left_0 >= $.right_0) ? 'true' : 'false'",
                "decisionCases": {"true": [], "false": []},
            },
        ]
    }
    validate_and_compile_workflow_data_contract(
        candidate,
        {"data_contract": contract()},
        atom_catalog=CATALOG,
        strict=True,
    )

    candidate["tasks"][1]["inputParameters"]["left_0"] = "${missing.output.count}"
    with pytest.raises(DefinitionValidationError, match="数据引用不存在"):
        validate_and_compile_workflow_data_contract(
            candidate,
            {"data_contract": contract()},
            atom_catalog=CATALOG,
            strict=True,
        )


def test_condition_rejects_numeric_operator_for_string_reference():
    candidate = {
        "tasks": [
            {
                "name": "condition",
                "taskReferenceName": "condition_1",
                "type": "SWITCH",
                "inputParameters": {"left_0": "${workflow.input.service}", "right_0": "z"},
                "evaluatorType": "javascript",
                "expression": "($.left_0 > $.right_0) ? 'true' : 'false'",
                "decisionCases": {"true": [], "false": []},
            }
        ]
    }
    with pytest.raises(DefinitionValidationError, match="数值类型"):
        validate_and_compile_workflow_data_contract(
            candidate,
            {"data_contract": contract()},
            atom_catalog=CATALOG,
            strict=True,
        )


@pytest.mark.parametrize(
    "expression",
    [
        "($.left_0.indexOf($.right_0) < 0) ? 'true' : 'false'",
        "($.left_0.indexOf($.right_0) == 0) ? 'true' : 'false'",
        "($.left_0.slice($.left_0.length - $.right_0.length) == $.right_0) ? 'true' : 'false'",
    ],
)
def test_condition_accepts_migrated_string_operators(expression):
    candidate = {
        "tasks": [
            {
                "name": "condition",
                "taskReferenceName": "condition_1",
                "type": "SWITCH",
                "inputParameters": {"left_0": "${workflow.input.service}", "right_0": "ops"},
                "evaluatorType": "javascript",
                "expression": expression,
                "decisionCases": {"true": [], "false": []},
            }
        ]
    }

    validate_and_compile_workflow_data_contract(
        candidate,
        {"data_contract": contract()},
        atom_catalog=CATALOG,
        strict=True,
    )


def test_sensitive_reference_requires_secret_compatible_and_cannot_be_templated():
    valid = definition({"secret": "${workflow.input.api_token}"})
    validate_and_compile_workflow_data_contract(valid, {"data_contract": contract()}, atom_catalog=CATALOG, strict=True)

    invalid = definition({"label": "token=${workflow.input.api_token}"})
    with pytest.raises(DefinitionValidationError, match="文本模板不能使用敏感值"):
        validate_and_compile_workflow_data_contract(invalid, {"data_contract": contract()}, atom_catalog=CATALOG, strict=True)

    control_flow = {
        "tasks": [
            {
                "name": "condition",
                "taskReferenceName": "condition_1",
                "type": "SWITCH",
                "inputParameters": {"switchCaseValue": "${workflow.input.api_token}"},
                "decisionCases": {"yes": []},
            }
        ]
    }
    with pytest.raises(DefinitionValidationError, match="敏感值不能用于控制流"):
        validate_and_compile_workflow_data_contract(
            control_flow,
            {"data_contract": contract()},
            atom_catalog=CATALOG,
            strict=True,
        )


def test_sensitive_input_is_redacted_without_mutating_other_values():
    result = redact_sensitive_inputs(
        {"service": "billing", "api_token": "secret-value", "__system": {"execution_id": "e-1"}},
        {"data_contract": contract()},
    )
    assert result == {"service": "billing", "api_token": "***", "__system": {"execution_id": "e-1"}}


def test_runtime_input_uses_declared_literal_default_without_treating_empty_as_missing():
    schema = {
        "type": "object",
        "properties": {"region": {"type": "string", "default": "cn"}, "label": {"type": "string", "default": "fallback"}},
        "required": ["region"],
        "additionalProperties": False,
    }

    assert validate_workflow_inputs({"label": ""}, schema) == {"region": "cn", "label": ""}


def test_legacy_constants_and_outputs_are_rejected():
    data_contract = contract()
    data_contract["constants"] = [{"parameterId": "constant:limit", "key": "limit", "name": "限制", "schema": {"type": "integer"}, "value": 10}]

    with pytest.raises(DefinitionValidationError, match="设置数据和对应的 Return"):
        validate_and_compile_workflow_data_contract(
            definition({"value": 1}),
            {"data_contract": data_contract},
            atom_catalog=CATALOG,
            strict=True,
        )


@pytest.mark.django_db
def test_runtime_persists_redacted_sensitive_input_and_sends_encrypted_envelope_to_engine(mocker):
    metadata = {"data_contract": contract()}
    workflow = Workflow.objects.create(
        name="敏感输入流程",
        team=[7],
        definition=definition({"secret": "${workflow.input.api_token}"}),
        current_version=1,
        status=Workflow.Status.PUBLISHED,
        enabled=True,
    )
    WorkflowVersion.objects.create(
        workflow=workflow,
        version=1,
        definition=workflow.definition,
        canvas_metadata=metadata,
    )
    conductor = mocker.Mock()
    conductor.start_workflow.return_value = "conductor-sensitive-1"

    execution = start_execution(
        workflow,
        inputs={"service": "billing", "api_token": "secret-value"},
        started_by="alice",
        domain="example.com",
        client=conductor,
    )

    assert execution.input["api_token"] == "***"
    conductor_token = conductor.start_workflow.call_args.kwargs["inputs"]["api_token"]
    assert conductor_token != "secret-value"
    assert resolve_secret_envelopes(conductor_token) == "secret-value"
    assert execution.input["__system"]["workflow_id"] == str(workflow.pk)
