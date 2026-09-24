import pytest

from apps.workflow_orchestration.services.definitions import DefinitionValidationError
from apps.workflow_orchestration.services.orchestration_contract import validate_orchestration_metadata


def _metadata(trigger_type="FORM", return_type=None, *, response_mode="WAIT"):
    trigger = {
        "id": "trigger_1",
        "name": "触发",
        "trigger_type": trigger_type,
        "input_schema": {"type": "object", "properties": {"target": {"type": "string"}}},
        "config": {"response_mode": response_mode} if trigger_type == "WEBHOOK" else {},
    }
    returns = [] if return_type is None else [{"id": "return_1", "name": "响应", "return_type": return_type, "config": {"body": "${task.output}"}}]
    edges = [{"id": "in", "source": "trigger_1", "target": "task"}]
    if returns:
        edges.append({"id": "out", "source": "task", "target": "return_1"})
    return {"trigger_nodes": [trigger], "return_nodes": returns, "edges": edges}


def test_form_trigger_finishes_without_return_and_promotes_its_schema():
    metadata = validate_orchestration_metadata(_metadata(), task_references={"task"})

    assert metadata["input_schema"]["properties"]["target"]["type"] == "string"
    assert metadata["return_nodes"] == []


def test_removed_form_return_is_rejected():
    with pytest.raises(DefinitionValidationError, match="Return.*类型非法"):
        validate_orchestration_metadata(_metadata("FORM", "FORM"), task_references={"task"})


def test_form_field_extensions_become_runtime_contract_without_legacy_ui_metadata():
    metadata = _metadata("FORM", None)
    metadata["trigger_nodes"][0]["input_schema"]["properties"] = {
        "targets": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 10,
            "x-widget": "target-selector",
            "x-target-binding": {
                "mode": "runtime",
                "allowedSources": ["job_mgmt"],
                "allowedOperatingSystems": ["linux", "windows"],
                "minCount": 1,
                "maxCount": 10,
            },
        }
    }

    normalized = validate_orchestration_metadata(metadata, task_references={"task"})

    contract_input = normalized["data_contract"]["inputs"][0]
    assert contract_input["ui"]["widget"] == "target-selector"
    assert contract_input["ui"]["targetBinding"]["allowedSources"] == ["job_mgmt"]
    assert normalized["input_ui_schema"]["targets"] == {"ui:widget": "target-selector"}


def test_form_trigger_can_finish_at_last_task_without_return_node():
    metadata = validate_orchestration_metadata(_metadata("FORM", None), task_references={"task"})

    assert metadata["return_nodes"] == []
    assert metadata["edges"] == [{"id": "in", "source": "trigger_1", "target": "task"}]


@pytest.mark.parametrize(
    ("trigger_type", "return_type", "response_mode"),
    [
        ("FORM", "WEBHOOK", "WAIT"),
        ("SCHEDULE", "WEBHOOK", "WAIT"),
        ("WEBHOOK", "WEBHOOK", "IMMEDIATE"),
    ],
)
def test_incompatible_return_paths_are_rejected(trigger_type, return_type, response_mode):
    with pytest.raises(DefinitionValidationError):
        validate_orchestration_metadata(
            _metadata(trigger_type, return_type, response_mode=response_mode),
            task_references={"task"},
        )


def test_canvas_must_be_a_dag():
    metadata = _metadata("WEBHOOK", "WEBHOOK")
    metadata["edges"].append({"id": "cycle", "source": "return_1", "target": "trigger_1"})

    with pytest.raises(DefinitionValidationError, match="环|触发节点不能有入边|Return 节点不能有出边"):
        validate_orchestration_metadata(metadata, task_references={"task"})


def test_every_trigger_path_must_finish_at_its_return():
    metadata = _metadata("WEBHOOK", "WEBHOOK")
    metadata["edges"].append({"id": "dangling", "source": "trigger_1", "target": "other"})

    with pytest.raises(DefinitionValidationError, match="未连接到 Return"):
        validate_orchestration_metadata(metadata, task_references={"task", "other"})


def test_orphan_nodes_are_rejected():
    metadata = _metadata("FORM", None)

    with pytest.raises(DefinitionValidationError, match="未连接到任何触发器"):
        validate_orchestration_metadata(metadata, task_references={"task", "orphan"})


def test_platform_owned_webhook_body_is_not_mistaken_for_a_shared_form_input():
    metadata = _metadata("FORM", None)
    metadata["trigger_nodes"].append(
        {
            "id": "trigger_2",
            "name": "Webhook 触发",
            "trigger_type": "WEBHOOK",
            "input_schema": {
                "type": "object",
                "properties": {"target": {"type": "string"}, "private_value": {"type": "integer"}},
                "required": ["target", "private_value"],
            },
            "config": {"response_mode": "WAIT"},
        }
    )
    metadata["return_nodes"].append({"id": "return_2", "name": "Webhook 响应", "return_type": "WEBHOOK", "config": {"body": "${other.output}"}})
    metadata["edges"].extend(
        [
            {"id": "in-2", "source": "trigger_2", "target": "other"},
            {"id": "out-2", "source": "other", "target": "return_2"},
        ]
    )

    normalized = validate_orchestration_metadata(metadata, task_references={"task", "other"})

    assert normalized["data_contract"]["inputs"] == []
    assert normalized["data_contract"]["constants"] == []
    assert normalized["data_contract"]["outputs"] == []


def test_nats_trigger_is_an_engine_entry_without_return_node():
    metadata = _metadata("NATS", None)
    metadata["trigger_nodes"][0]["input_schema"] = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": True,
    }
    metadata["trigger_nodes"][0]["config"] = {}

    normalized = validate_orchestration_metadata(metadata, task_references={"task"})

    assert normalized["trigger_nodes"][0]["trigger_type"] == "NATS"


def test_nats_trigger_rejects_user_configured_subject():
    metadata = _metadata("NATS", None)
    metadata["trigger_nodes"][0]["config"] = {"subject": "bklite.workflow.7.trigger_nats"}

    with pytest.raises(DefinitionValidationError, match="NATS.*不需要配置参数"):
        validate_orchestration_metadata(metadata, task_references={"task"})


def test_nats_rejects_user_configured_idempotency_field():
    metadata = _metadata("NATS", None)
    metadata["trigger_nodes"][0]["config"] = {
        "idempotency_field": "missing_id",
    }

    with pytest.raises(DefinitionValidationError, match="不需要配置参数"):
        validate_orchestration_metadata(metadata, task_references={"task"})


def test_webhook_without_explicit_response_mode_defaults_to_immediate():
    metadata = _metadata("WEBHOOK", None)
    metadata["trigger_nodes"][0]["config"] = {}

    normalized = validate_orchestration_metadata(metadata, task_references={"task"})

    assert normalized["return_nodes"] == []


def test_webhook_uses_platform_owned_request_body_schema():
    metadata = _metadata("WEBHOOK", "WEBHOOK")

    normalized = validate_orchestration_metadata(metadata, task_references={"task"})

    assert normalized["trigger_nodes"][0]["input_schema"] == {
        "type": "object",
        "properties": {
            "body": {
                "type": "object",
                "title": "请求正文",
                "properties": {},
                "additionalProperties": True,
            }
        },
        "required": ["body"],
        "additionalProperties": False,
    }


def test_wait_webhook_must_converge_to_one_response_node():
    metadata = _metadata("WEBHOOK", "WEBHOOK")
    metadata["return_nodes"].append({"id": "return_2", "name": "另一个响应", "return_type": "WEBHOOK", "config": {"body": "${task.output}"}})
    metadata["edges"].append({"id": "out-2", "source": "task", "target": "return_2"})

    with pytest.raises(DefinitionValidationError, match="只能到达一个 Webhook 响应节点"):
        validate_orchestration_metadata(metadata, task_references={"task"})
