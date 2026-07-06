from dataclasses import dataclass

from apps.monitor.expression.ast import BinaryOpNode, ExpressionNode, NumberNode, VariableNode
from apps.monitor.expression.conditions import compile_filter_to_query
from apps.monitor.expression.validators import validate_formula_condition


@dataclass(frozen=True)
class CompiledFormula:
    query: str
    result_name: str
    group_by: list[str]
    warnings: list[dict]
    anchor_ref: str


class FormulaCompiler:
    def __init__(self, query_condition: dict, metrics_by_id: dict[int, object]):
        self.query_condition = query_condition
        self.metrics_by_id = metrics_by_id
        self.validation = validate_formula_condition(query_condition)
        self.inputs = {item["ref"]: item for item in query_condition["queries"]}
        self.anchor_group_by = self.inputs[self.validation.anchor_ref]["group_by"]

    def compile(self) -> CompiledFormula:
        query = self._compile_node(self.validation.ast)
        return CompiledFormula(
            query=query,
            result_name=self.query_condition["result_name"],
            group_by=list(self.anchor_group_by),
            warnings=self.validation.warnings,
            anchor_ref=self.validation.anchor_ref,
        )

    def _compile_node(self, node: ExpressionNode) -> str:
        if isinstance(node, NumberNode):
            return str(node.value)
        if isinstance(node, VariableNode):
            return self._compile_variable(node.name)
        if isinstance(node, BinaryOpNode):
            left = self._compile_node(node.left)
            right = self._compile_node(node.right)
            modifier = self._match_modifier(node.left, node.right)
            return f"({left} {node.operator}{modifier} {right})"
        raise TypeError(f"Unsupported expression node: {type(node)!r}")

    def _compile_variable(self, ref: str) -> str:
        item = self.inputs[ref]
        metric = self.metrics_by_id[item["metric_id"]]
        base_query = compile_filter_to_query(metric.query, item.get("filter") or [])
        group_by = ",".join(item.get("group_by") or [])
        return f"{item['group_algorithm']}({base_query}) by ({group_by})"

    def _match_modifier(self, left: ExpressionNode, right: ExpressionNode) -> str:
        left_ref = self._first_variable(left)
        right_ref = self._first_variable(right)
        if not left_ref or not right_ref:
            return ""

        left_group = set(self.inputs[left_ref]["group_by"])
        right_group = set(self.inputs[right_ref]["group_by"])
        if left_group == right_group:
            return ""
        if not right_group.issubset(left_group):
            return ""

        common = [label for label in self.inputs[left_ref]["group_by"] if label in right_group]
        if not common:
            return ""
        return f" on({','.join(common)}) group_left"

    def _first_variable(self, node: ExpressionNode) -> str | None:
        if isinstance(node, VariableNode):
            return node.name
        if isinstance(node, BinaryOpNode):
            return self._first_variable(node.left) or self._first_variable(node.right)
        return None
