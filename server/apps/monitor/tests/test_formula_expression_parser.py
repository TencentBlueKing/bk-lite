import pytest

from apps.monitor.expression.ast import BinaryOpNode, NumberNode, VariableNode
from apps.monitor.expression.errors import FormulaSyntaxError
from apps.monitor.expression.parser import parse_expression


def test_parse_operator_precedence():
    node = parse_expression("a / b * 100")

    assert isinstance(node, BinaryOpNode)
    assert node.operator == "*"
    assert isinstance(node.right, NumberNode)
    assert node.right.value == 100
    assert isinstance(node.left, BinaryOpNode)
    assert node.left.operator == "/"
    assert isinstance(node.left.left, VariableNode)
    assert node.left.left.name == "a"
    assert isinstance(node.left.right, VariableNode)
    assert node.left.right.name == "b"


def test_parse_parentheses():
    node = parse_expression("(a + b) / c")

    assert isinstance(node, BinaryOpNode)
    assert node.operator == "/"
    assert isinstance(node.left, BinaryOpNode)
    assert node.left.operator == "+"
    assert isinstance(node.right, VariableNode)
    assert node.right.name == "c"


def test_reject_unknown_character():
    with pytest.raises(FormulaSyntaxError) as exc:
        parse_expression("a / b; drop")

    assert "非法字符" in str(exc.value)


def test_reject_unclosed_parentheses():
    with pytest.raises(FormulaSyntaxError) as exc:
        parse_expression("(a / b")

    assert "括号" in str(exc.value)
