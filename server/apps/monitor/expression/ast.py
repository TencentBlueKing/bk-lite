from dataclasses import dataclass


class ExpressionNode:
    pass


@dataclass(frozen=True)
class NumberNode(ExpressionNode):
    value: float | int


@dataclass(frozen=True)
class VariableNode(ExpressionNode):
    name: str


@dataclass(frozen=True)
class BinaryOpNode(ExpressionNode):
    operator: str
    left: ExpressionNode
    right: ExpressionNode
