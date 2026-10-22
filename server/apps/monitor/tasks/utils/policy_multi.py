"""多指标条件的条件级策略视图。判定与编译只读 queries[]。"""

from apps.monitor.tasks.utils.policy_methods import (
    compile_existence_query,
    compile_policy_query,
    compile_window_query,
)


def is_multi_query(query_condition) -> bool:
    return isinstance(query_condition, dict) and query_condition.get("type") == "multi"


def multi_queries(query_condition) -> list[dict]:
    queries = (query_condition or {}).get("queries") if isinstance(query_condition, dict) else None
    if not isinstance(queries, list):
        return []
    return [item for item in queries if isinstance(item, dict)]


def first_level_query(query_condition) -> dict:
    for item in multi_queries(query_condition):
        if item.get("role") == "level":
            return item
    return {}


def is_formula_condition(condition) -> bool:
    return isinstance(condition, dict) and condition.get("source") == "formula"


def condition_metric_items(condition) -> list[dict]:
    """条件实际引用的指标条目。计算条件取操作数，原生条件取自身。"""
    if not isinstance(condition, dict):
        return []
    if is_formula_condition(condition):
        return [item for item in condition.get("operands") or [] if isinstance(item, dict)]
    return [condition]


def query_metric_items(query_condition) -> list[dict]:
    """模板与策略组要解析的指标条目，不含计算条件的结果名称。"""
    if not isinstance(query_condition, dict):
        return []
    if query_condition.get("type") == "formula":
        return [item for item in query_condition.get("queries") or [] if isinstance(item, dict)]
    if query_condition.get("type") == "multi":
        items = []
        for condition in multi_queries(query_condition):
            items.extend(condition_metric_items(condition))
        return items
    if query_condition.get("metric_id") or query_condition.get("metric_name"):
        return [query_condition]
    return []


def formula_query_condition(condition) -> dict:
    return {
        "type": "formula",
        "result_name": condition.get("metric_name") or "",
        "expression": condition.get("expression") or "",
        "queries": [item for item in condition.get("operands") or [] if isinstance(item, dict)],
    }


def condition_policy_like(policy, condition) -> dict:
    """把一个条件收成现有编译器接受的单指标或公式 policy_like。"""
    period = policy.get("period") if isinstance(policy, dict) else getattr(policy, "period", None)
    collect_type = policy.get("collect_type") if isinstance(policy, dict) else getattr(policy, "collect_type", "")
    policy_id = policy.get("id") if isinstance(policy, dict) else getattr(policy, "id", None)
    if is_formula_condition(condition):
        query_condition = formula_query_condition(condition)
    else:
        query_condition = {
            "type": "metric",
            "metric_id": condition.get("metric_id"),
            "filter": condition.get("filter") or [],
        }
    return {
        "id": policy_id,
        "algorithm": condition.get("algorithm") or "",
        "group_algorithm": condition.get("group_algorithm") or "",
        "group_by": list(condition.get("group_by") or []),
        "count_predicate": condition.get("count_predicate") or {},
        "compare_mode": "absolute",
        "compare_value_kind": "",
        "collect_type": collect_type or "",
        "period": period,
        "metric_unit": condition.get("metric_unit") or "",
        "calculation_unit": condition.get("calculation_unit") or "",
        "threshold_unit": condition.get("threshold_unit") or "",
        "query_condition": query_condition,
    }


def compile_condition_query(policy, condition, base_query, step, *, existence=False, window=False):
    policy_like = condition_policy_like(policy, condition)
    group_by = ",".join(condition.get("group_by") or [])
    if existence:
        return compile_existence_query(policy_like, base_query, step, group_by)
    if window:
        return compile_window_query(policy_like, base_query, step, group_by)
    return compile_policy_query(policy_like, base_query, step, group_by)
