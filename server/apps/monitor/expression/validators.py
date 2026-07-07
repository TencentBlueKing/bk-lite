import re
from dataclasses import dataclass

from apps.monitor.expression.ast import BinaryOpNode, ExpressionNode, VariableNode
from apps.monitor.expression.errors import FormulaValidationError
from apps.monitor.expression.parser import parse_expression


_VALID_GROUP_AGGREGATION_ALGORITHMS = {"sum", "avg", "max", "min", "count"}
_VALID_LABEL_METHODS = {"=", "!=", "=~", "!~"}
_LABEL_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


@dataclass(frozen=True)
class FormulaValidationResult:
    ast: ExpressionNode
    anchor_ref: str
    warnings: list[dict]


def collect_variables(node: ExpressionNode) -> list[str]:
    if isinstance(node, VariableNode):
        return [node.name]
    if isinstance(node, BinaryOpNode):
        return collect_variables(node.left) + collect_variables(node.right)
    return []


def _validate_filter(ref: str, filter_list: object) -> None:
    if filter_list is None:
        return
    if not isinstance(filter_list, list):
        raise FormulaValidationError(f"指标 {ref} 的 filter 必须是列表")

    for index, condition in enumerate(filter_list):
        if not isinstance(condition, dict):
            raise FormulaValidationError(f"指标 {ref} filter[{index}] 必须是对象")
        name = condition.get("name", "")
        method = condition.get("method", "")
        if not name:
            raise FormulaValidationError(f"指标 {ref} filter[{index}] 缺少 name")
        if not method:
            raise FormulaValidationError(f"指标 {ref} filter[{index}] 缺少 method")
        if "value" not in condition:
            raise FormulaValidationError(f"指标 {ref} filter[{index}] 缺少 value")
        if name and not _LABEL_NAME_RE.match(str(name)):
            raise FormulaValidationError(
                f"指标 {ref} filter[{index}].name={name!r} 包含非法字符，只允许 [a-zA-Z_][a-zA-Z0-9_]*"
            )
        if method and method not in _VALID_LABEL_METHODS:
            raise FormulaValidationError(
                f"指标 {ref} filter[{index}].method={method!r} 不是合法运算符，只允许 {sorted(_VALID_LABEL_METHODS)}"
            )


def _validate_group_by(ref: str, group_by: object) -> list[str]:
    if not isinstance(group_by, list) or not group_by:
        raise FormulaValidationError(f"指标 {ref} 缺少 group_by")
    if not all(isinstance(item, str) and item for item in group_by):
        raise FormulaValidationError(f"指标 {ref} group_by 必须是非空字符串列表")
    return group_by


def _normalize_metric_id(ref: str, value: object) -> int:
    if value is None or value == "":
        raise FormulaValidationError(f"指标 {ref} 缺少 metric_id")
    if isinstance(value, bool):
        raise FormulaValidationError(f"指标 {ref} metric_id 必须是正整数")
    if isinstance(value, int):
        metric_id = value
    elif isinstance(value, str) and value.strip().isdigit():
        metric_id = int(value.strip())
    else:
        raise FormulaValidationError(f"指标 {ref} metric_id 必须是正整数")
    if metric_id <= 0:
        raise FormulaValidationError(f"指标 {ref} metric_id 必须是正整数")
    return metric_id


def validate_formula_condition(query_condition: dict) -> FormulaValidationResult:
    if query_condition.get("type") != "formula":
        raise FormulaValidationError("query_condition.type 必须为 formula")
    if not query_condition.get("result_name"):
        raise FormulaValidationError("多指标策略必须填写结果名称")

    ast = parse_expression(query_condition.get("expression") or "")
    queries = query_condition.get("queries")
    if not isinstance(queries, list) or len(queries) < 2:
        raise FormulaValidationError("多指标策略至少需要两个指标")

    by_ref: dict[str, dict] = {}
    for index, item in enumerate(queries):
        if not isinstance(item, dict):
            raise FormulaValidationError(f"queries[{index}] 必须是对象")
        ref = str(item.get("ref") or "")
        if not ref:
            raise FormulaValidationError(f"queries[{index}].ref 不能为空")
        if ref in by_ref:
            raise FormulaValidationError(f"指标变量 {ref} 重复")
        item["metric_id"] = _normalize_metric_id(ref, item.get("metric_id"))
        group_algorithm = item.get("group_algorithm")
        if not group_algorithm:
            raise FormulaValidationError(f"指标 {ref} 缺少 group_algorithm")
        if group_algorithm not in _VALID_GROUP_AGGREGATION_ALGORITHMS:
            raise FormulaValidationError(
                f"指标 {ref} group_algorithm 非法，须为 {sorted(_VALID_GROUP_AGGREGATION_ALGORITHMS)} 之一"
            )
        _validate_group_by(ref, item.get("group_by"))
        _validate_filter(ref, item.get("filter", []))
        by_ref[ref] = item

    variables = collect_variables(ast)
    if not variables:
        raise FormulaValidationError("表达式必须引用指标变量")
    unique_variables = list(dict.fromkeys(variables))
    if len(unique_variables) < 2:
        raise FormulaValidationError("表达式至少引用两个指标变量")
    for ref in variables:
        if ref not in by_ref:
            raise FormulaValidationError(f"表达式引用了不存在的指标变量 {ref}")

    unused_refs = sorted(set(by_ref) - set(unique_variables))
    if unused_refs:
        raise FormulaValidationError(f"指标变量 {', '.join(unused_refs)} 未被表达式引用")

    anchor_ref = unique_variables[0]
    anchor_group_by = set(by_ref[anchor_ref].get("group_by") or [])
    warnings: list[dict] = []
    for ref in unique_variables[1:]:
        group_by = set(by_ref[ref].get("group_by") or [])
        extra = sorted(group_by - anchor_group_by)
        if extra:
            raise FormulaValidationError(f"指标 {ref} 包含锚点外额外维度：{', '.join(extra)}")
        if group_by != anchor_group_by and "instance_id" not in group_by:
            warnings.append(
                {
                    "code": "FORMULA_DIMENSION_REUSE",
                    "message": f"指标 {ref} 将按 {', '.join(sorted(group_by))} 对齐，并跨缺失维度复用数据",
                }
            )

    return FormulaValidationResult(ast=ast, anchor_ref=anchor_ref, warnings=warnings)
