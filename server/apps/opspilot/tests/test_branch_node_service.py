"""分支节点：内置操作符、triggerType、变量回退、安全求值失败返回 False。"""
import pytest

from apps.opspilot.utils.chat_flow_utils.nodes.condition.branch import BranchNode, ConditionNode

pytestmark = pytest.mark.unit


class _VM:
    def __init__(self, variables):
        self._variables = variables

    def get_all_variables(self):
        return self._variables


def _cfg(**overrides):
    config = {
        "inputParams": "last_message",
        "outputParams": "last_message",
        "conditionField": "status",
        "conditionOperator": "equals",
        "conditionValue": "ok",
    }
    config.update(overrides)
    return {"data": {"config": config}}


def test_equals_uses_variable_and_returns_condition_result():
    node = BranchNode(_VM({"status": "ok"}))
    out = node.execute("n1", _cfg(), {"last_message": "ignored"})
    assert out == {"last_message": True, "condition_result": True}


def test_operators_not_equals_contains_starts_and_ends():
    node = BranchNode(_VM({}))
    assert (
        node.execute("n", _cfg(conditionField="missing", conditionOperator="!=", conditionValue="x"), {"last_message": "y"})["condition_result"]
        is True
    )
    assert (
        node.execute(
            "n",
            _cfg(conditionField="missing", conditionOperator="contains", conditionValue="ab"),
            {"last_message": "xxabxx"},
        )["condition_result"]
        is True
    )
    assert (
        node.execute(
            "n",
            _cfg(conditionField="missing", conditionOperator="not_contains", conditionValue="z"),
            {"last_message": "abc"},
        )["condition_result"]
        is True
    )
    assert (
        node.execute(
            "n",
            _cfg(conditionField="missing", conditionOperator="starts_with", conditionValue="he"),
            {"last_message": "hello"},
        )["condition_result"]
        is True
    )
    assert (
        node.execute(
            "n",
            _cfg(conditionField="missing", conditionOperator="ends_with", conditionValue="lo"),
            {"last_message": "hello"},
        )["condition_result"]
        is True
    )


def test_trigger_type_prefers_start_node_id_then_variable():
    node = BranchNode(_VM({"start_node": "from-var"}), start_node_id="from-init")
    out = node.execute("n", _cfg(conditionField="triggerType", conditionValue="from-init"), {"last_message": ""})
    assert out["condition_result"] is True

    fallback = BranchNode(_VM({"start_node": "from-var"}))
    out = fallback.execute("n", _cfg(conditionField="triggerType", conditionValue="from-var"), {"last_message": ""})
    assert out["condition_result"] is True


def test_unknown_operator_falls_back_to_safe_eval_and_swallows_error():
    node = BranchNode(_VM({}))
    false_out = node.execute(
        "n",
        _cfg(conditionField="missing", conditionOperator="not a valid op", conditionValue="x"),
        {"last_message": "y"},
    )
    assert false_out == {"last_message": False, "condition_result": False}


def test_condition_node_alias_is_branch_node():
    assert ConditionNode is BranchNode
    assert isinstance(ConditionNode(_VM({})), BranchNode)
