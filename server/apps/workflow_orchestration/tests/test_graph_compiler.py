import pytest

from apps.workflow_orchestration.services.definitions import DefinitionValidationError
from apps.workflow_orchestration.services.graph_compiler import compile_canvas_graph


def _definition(*references):
    return {
        "name": "draft",
        "version": 1,
        "schemaVersion": 2,
        "tasks": [
            {
                "name": "bklite_notification",
                "taskReferenceName": reference,
                "type": "SIMPLE",
                "inputParameters": {
                    "notification_type": "EMAIL",
                    "channel_id": 1,
                    "body": reference,
                },
            }
            for reference in references
        ],
    }


def _metadata(edges):
    return {
        "control_flow_mode": "EDGES",
        "trigger_nodes": [{"id": "trigger_form"}],
        "return_nodes": [],
        "edges": edges,
    }


def test_linear_edges_define_execution_order_without_reordering_authored_nodes():
    definition = _definition("third", "first", "second")
    metadata = _metadata(
        [
            {"source": "trigger_form", "target": "first"},
            {"source": "first", "target": "second"},
            {"source": "second", "target": "third"},
        ]
    )

    compiled = compile_canvas_graph(definition, metadata)

    assert [task["taskReferenceName"] for task in compiled["tasks"]] == ["first", "second", "third"]
    assert [task["taskReferenceName"] for task in definition["tasks"]] == ["third", "first", "second"]


def test_parallel_edges_generate_hidden_conductor_fork_and_join():
    definition = _definition("start", "left", "right", "finish")
    metadata = _metadata(
        [
            {"source": "trigger_form", "target": "start"},
            {"source": "start", "target": "left"},
            {"source": "start", "target": "right"},
            {"source": "left", "target": "finish"},
            {"source": "right", "target": "finish"},
        ]
    )

    compiled = compile_canvas_graph(definition, metadata)

    assert [task["type"] for task in compiled["tasks"]] == ["SIMPLE", "FORK_JOIN", "JOIN", "SIMPLE"]
    assert [[item["taskReferenceName"] for item in branch] for branch in compiled["tasks"][1]["forkTasks"]] == [["left"], ["right"]]
    assert compiled["tasks"][2]["joinOn"] == ["left", "right"]
    assert all(not task["taskReferenceName"].startswith("__auto_") for task in definition["tasks"])


def test_edge_mode_rejects_hand_authored_engine_fork_nodes():
    definition = _definition("start")
    definition["tasks"][0]["type"] = "FORK_JOIN"

    with pytest.raises(DefinitionValidationError, match="不允许手工配置"):
        compile_canvas_graph(definition, _metadata([{"source": "trigger_form", "target": "start"}]))


def test_switch_keeps_a_branch_that_finishes_directly_at_webhook_return_node():
    definition = _definition("condition", "notify")
    definition["tasks"][0].update(
        name="condition",
        type="SWITCH",
        inputParameters={"left_0": "${system.execution_id}", "right_0": ""},
        evaluatorType="javascript",
        expression="($.left_0 == $.right_0) ? 'true' : 'false'",
        decisionCases={"true": [], "false": []},
        defaultCase=[],
    )
    metadata = _metadata(
        [
            {"source": "trigger_form", "target": "condition"},
            {"source": "condition", "sourceHandle": "true", "target": "notify"},
            {"source": "condition", "sourceHandle": "false", "target": "return_webhook"},
            {"source": "notify", "target": "return_webhook"},
        ]
    )
    metadata["return_nodes"] = [{"id": "return_webhook"}]

    compiled = compile_canvas_graph(definition, metadata)

    condition = compiled["tasks"][0]
    assert [task["taskReferenceName"] for task in condition["decisionCases"]["true"]] == ["notify"]
    assert condition["decisionCases"]["false"] == []
