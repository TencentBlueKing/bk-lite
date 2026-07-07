from dataclasses import dataclass

from apps.monitor.expression.ast import BinaryOpNode, ExpressionNode, NumberNode, VariableNode
from apps.monitor.expression.conditions import compile_filter_to_query
from apps.monitor.expression.errors import FormulaCompileError
from apps.monitor.expression.validators import validate_formula_condition


@dataclass(frozen=True)
class CompiledFormula:
    query: str
    result_name: str
    group_by: list[str]
    warnings: list[dict]
    anchor_ref: str


@dataclass(frozen=True)
class _CompiledNode:
    query: str
    group_by: list[str]


class FormulaCompiler:
    def __init__(self, query_condition: dict, metrics_by_id: dict[int, object]):
        self.query_condition = query_condition
        self.metrics_by_id = metrics_by_id
        self.validation = validate_formula_condition(query_condition)
        self.inputs = {item["ref"]: item for item in query_condition["queries"]}
        self.anchor_group_by = self.inputs[self.validation.anchor_ref]["group_by"]

    def compile(self) -> CompiledFormula:
        compiled = self._compile_node(self.validation.ast)
        if compiled.group_by != self.anchor_group_by:
            raise FormulaCompileError("公式结果维度必须与锚点指标维度一致")
        return CompiledFormula(
            query=compiled.query,
            result_name=self.query_condition["result_name"],
            group_by=list(compiled.group_by),
            warnings=self.validation.warnings,
            anchor_ref=self.validation.anchor_ref,
        )

    def _compile_node(self, node: ExpressionNode) -> _CompiledNode:
        if isinstance(node, NumberNode):
            return _CompiledNode(query=str(node.value), group_by=[])
        if isinstance(node, VariableNode):
            return self._compile_variable(node.name)
        if isinstance(node, BinaryOpNode):
            left = self._compile_node(node.left)
            right = self._compile_node(node.right)
            modifier, group_by = self._match_modifier(left.group_by, right.group_by)
            return _CompiledNode(query=f"({left.query} {node.operator}{modifier} {right.query})", group_by=group_by)
        raise TypeError(f"Unsupported expression node: {type(node)!r}")

    def _compile_variable(self, ref: str) -> _CompiledNode:
        item = self.inputs[ref]
        metric = self.metrics_by_id[item["metric_id"]]
        base_query = compile_filter_to_query(metric.query, item.get("filter") or [])
        group_by = item.get("group_by") or []
        group_by_clause = ",".join(group_by)
        return _CompiledNode(query=f"{item['group_algorithm']}({base_query}) by ({group_by_clause})", group_by=list(group_by))

    def _match_modifier(self, left_group_by: list[str], right_group_by: list[str]) -> tuple[str, list[str]]:
        if not left_group_by:
            return "", list(right_group_by)
        if not right_group_by:
            return "", list(left_group_by)

        left_group = set(left_group_by)
        right_group = set(right_group_by)
        if left_group == right_group:
            return "", list(left_group_by)
        if right_group.issubset(left_group):
            common = [label for label in left_group_by if label in right_group]
            return f" on({','.join(common)}) group_left", list(left_group_by)
        if left_group.issubset(right_group):
            common = [label for label in right_group_by if label in left_group]
            return f" on({','.join(common)}) group_right", list(right_group_by)
        raise FormulaCompileError("无法匹配维度：公式左右两侧指标维度不兼容")
