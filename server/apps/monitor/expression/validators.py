import math
import re
from dataclasses import dataclass

from apps.monitor.constants.alert_policy import AlertConstants
from apps.monitor.expression.ast import BinaryOpNode, ExpressionNode, VariableNode
from apps.monitor.expression.errors import FormulaError, FormulaValidationError, MultiValidationError
from apps.monitor.expression.parser import parse_expression
from apps.monitor.tasks.utils.policy_methods import (
    COUNT_IF_ALGORITHM,
    PER_SERIES_ALGORITHMS,
    POLICY_ALGORITHMS,
    PREDICATE_TO_PROMQL,
)


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
        if isinstance(condition.get("value"), (list, tuple, set, dict)):
            raise FormulaValidationError(f"指标 {ref} filter[{index}].value 必须是标量")
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
    invalid_items = [item for item in group_by if not _LABEL_NAME_RE.match(item)]
    if invalid_items:
        raise FormulaValidationError(f"指标 {ref} group_by 包含非法字符：{', '.join(invalid_items)}")
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

    anchor_ref = str(queries[0].get("ref") or "")
    anchor_group_by = set(by_ref[anchor_ref].get("group_by") or [])
    if "instance_id" not in anchor_group_by:
        raise FormulaValidationError("公式锚点指标 group_by 必须包含 instance_id")
    warnings: list[dict] = []
    for ref in unique_variables:
        if ref == anchor_ref:
            continue
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


_MULTI_MIN_CONDITIONS = 2
_MULTI_MAX_CONDITIONS = 5
_MULTI_ROLES = {"level", "gate"}
_VALID_THRESHOLD_LEVELS = {"info", "warning", "error", "critical"}


@dataclass(frozen=True)
class MultiValidationResult:
    anchor_ref: str
    warnings: list[dict]


def _finite_number(raw_value):
    if isinstance(raw_value, bool):
        return None
    try:
        number = float(raw_value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _validate_count_predicate(ref: str, predicate: object) -> None:
    if not isinstance(predicate, dict) or "method" not in predicate or "value" not in predicate:
        raise MultiValidationError(f"条件 {ref} 的条件计数必须填写内阈运算符与值")
    if predicate.get("method") not in PREDICATE_TO_PROMQL:
        raise MultiValidationError(f"条件 {ref} 的条件计数内阈运算符非法")
    if _finite_number(predicate.get("value")) is None:
        raise MultiValidationError(f"条件 {ref} 的条件计数内阈必须是有限数值")


def _validate_level_threshold(ref: str, threshold: object) -> None:
    if not isinstance(threshold, list) or not threshold:
        raise MultiValidationError(f"条件 {ref} 至少需要一条阈值")
    valid_methods = set(AlertConstants.THRESHOLD_METHODS)
    seen_levels = set()
    for index, item in enumerate(threshold):
        if not isinstance(item, dict):
            raise MultiValidationError(f"条件 {ref} threshold[{index}] 必须是对象")
        if item.get("method") not in valid_methods:
            raise MultiValidationError(f"条件 {ref} threshold[{index}].method 非法")
        if _finite_number(item.get("value")) is None:
            raise MultiValidationError(f"条件 {ref} threshold[{index}].value 必须是有限数值")
        level = item.get("level")
        if level not in _VALID_THRESHOLD_LEVELS:
            raise MultiValidationError(f"条件 {ref} threshold[{index}].level 非法")
        if level in seen_levels:
            raise MultiValidationError(f"条件 {ref} 的级别 {level} 重复")
        seen_levels.add(level)


def _validate_gate_threshold(ref: str, threshold: object) -> None:
    if not isinstance(threshold, list) or len(threshold) != 1:
        raise MultiValidationError(f"条件 {ref} 的前置条件只能有一条阈值")
    item = threshold[0]
    if not isinstance(item, dict):
        raise MultiValidationError(f"条件 {ref} 的前置条件阈值必须是对象")
    if "level" in item:
        raise MultiValidationError(f"条件 {ref} 的前置条件阈值不能带级别")
    if item.get("method") not in set(AlertConstants.THRESHOLD_METHODS):
        raise MultiValidationError(f"条件 {ref} 的前置条件阈值运算符非法")
    if _finite_number(item.get("value")) is None:
        raise MultiValidationError(f"条件 {ref} 的前置条件阈值必须是有限数值")


def _validate_formula_multi_item(item: dict) -> None:
    ref = str(item.get("ref") or "")
    if not str(item.get("metric_name") or "").strip():
        raise MultiValidationError(f"条件 {ref} 必须填写结果名称")
    algorithm = item.get("algorithm")
    if algorithm not in POLICY_ALGORITHMS:
        raise MultiValidationError(f"条件 {ref} algorithm 非法")
    if algorithm in PER_SERIES_ALGORITHMS:
        raise MultiValidationError(f"条件 {ref} 不能使用逐序列算法")
    if algorithm == COUNT_IF_ALGORITHM:
        _validate_count_predicate(ref, item.get("count_predicate") or {})
    role = item.get("role")
    if role not in _MULTI_ROLES:
        raise MultiValidationError(f"条件 {ref} 的角色非法")
    if role == "level":
        _validate_level_threshold(ref, item.get("threshold"))
    else:
        _validate_gate_threshold(ref, item.get("threshold"))
    operands = item.get("operands")
    if not isinstance(operands, list) or len(operands) < 2:
        raise MultiValidationError(f"条件 {ref} 至少需要两个操作数")
    try:
        _validate_group_by(ref, item.get("group_by"))
    except FormulaValidationError as exc:
        raise MultiValidationError(str(exc)) from exc
    first = operands[0] if isinstance(operands[0], dict) else {}
    if list(item.get("group_by") or []) != list(first.get("group_by") or []):
        raise MultiValidationError(f"条件 {ref} 的 group_by 必须与第一个操作数一致")
    try:
        validate_formula_condition(
            {
                "type": "formula",
                "result_name": str(item.get("metric_name")).strip(),
                "expression": item.get("expression") or "",
                "queries": operands,
            }
        )
    except FormulaError as exc:
        raise MultiValidationError(str(exc)) from exc


def validate_multi_condition(query_condition: dict) -> MultiValidationResult:
    if not isinstance(query_condition, dict) or query_condition.get("type") != "multi":
        raise MultiValidationError("query_condition.type 必须为 multi")
    if not str(query_condition.get("result_name") or "").strip():
        raise MultiValidationError("多指标条件必须填写结果名称")
    if query_condition.get("combinator") != "all":
        raise MultiValidationError("多指标条件的组合方式只接受全部满足")

    queries = query_condition.get("queries")
    if not isinstance(queries, list) or not (_MULTI_MIN_CONDITIONS <= len(queries) <= _MULTI_MAX_CONDITIONS):
        raise MultiValidationError("多指标条件需要 2 到 5 个条件")

    by_ref: dict[str, dict] = {}
    for index, item in enumerate(queries):
        if not isinstance(item, dict):
            raise MultiValidationError(f"queries[{index}] 必须是对象")
        ref = str(item.get("ref") or "")
        if not ref:
            raise MultiValidationError(f"queries[{index}].ref 不能为空")
        if not _LABEL_NAME_RE.match(ref):
            raise MultiValidationError(f"条件变量 {ref} 包含非法字符")
        if ref in by_ref:
            raise MultiValidationError(f"条件变量 {ref} 重复")
        source = item.get("source") or "metric"
        if source not in {"metric", "formula"}:
            raise MultiValidationError(f"条件 {ref} 的来源非法")
        if source == "formula":
            _validate_formula_multi_item(item)
            by_ref[ref] = item
            continue
        item["metric_id"] = _normalize_metric_id(ref, item.get("metric_id"))
        group_algorithm = item.get("group_algorithm")
        if not group_algorithm:
            raise MultiValidationError(f"条件 {ref} 缺少 group_algorithm")
        if group_algorithm not in _VALID_GROUP_AGGREGATION_ALGORITHMS:
            raise MultiValidationError(
                f"条件 {ref} group_algorithm 非法，须为 {sorted(_VALID_GROUP_AGGREGATION_ALGORITHMS)} 之一"
            )
        _validate_group_by(ref, item.get("group_by"))
        _validate_filter(ref, item.get("filter", []))
        algorithm = item.get("algorithm")
        if algorithm not in POLICY_ALGORITHMS:
            raise MultiValidationError(f"条件 {ref} algorithm 非法")
        if algorithm == COUNT_IF_ALGORITHM:
            _validate_count_predicate(ref, item.get("count_predicate") or {})
        role = item.get("role")
        if role not in _MULTI_ROLES:
            raise MultiValidationError(f"条件 {ref} 的角色非法")
        if role == "level":
            _validate_level_threshold(ref, item.get("threshold"))
        else:
            _validate_gate_threshold(ref, item.get("threshold"))
        by_ref[ref] = item

    if not any(item.get("role") == "level" for item in queries):
        raise MultiValidationError("多指标条件至少需要一个参与级别的条件")

    anchor_ref = str(queries[0].get("ref") or "")
    anchor_group_by = list(by_ref[anchor_ref].get("group_by") or [])
    if "instance_id" not in anchor_group_by:
        raise MultiValidationError("多指标条件锚点 group_by 必须包含 instance_id")
    anchor_set = set(anchor_group_by)
    warnings: list[dict] = []
    for item in queries[1:]:
        ref = str(item.get("ref") or "")
        group_by = list(item.get("group_by") or [])
        extra = sorted(set(group_by) - anchor_set)
        if extra:
            raise MultiValidationError(f"条件 {ref} 包含锚点外额外维度：{', '.join(extra)}")
        if set(group_by) != anchor_set:
            warnings.append(
                {
                    "code": "MULTI_DIMENSION_REUSE",
                    "message": f"指标 {ref} 将按 {', '.join(sorted(group_by))} 对齐，并跨缺失维度复用数据",
                }
            )

    return MultiValidationResult(anchor_ref=anchor_ref, warnings=warnings)
