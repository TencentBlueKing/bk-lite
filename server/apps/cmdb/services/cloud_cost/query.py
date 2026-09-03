"""云成本图查询计划。

该模块把账单/流水权限、关联去重、聚合、排序和分页收敛为一个小接口。
调用方只提交报表语义；FalkorDB/Neo4j adapter 负责执行同一份参数化计划。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from apps.cmdb.constants.constants import INSTANCE, INSTANCE_ASSOCIATION


ReportKind = Literal["summary", "distribution", "bill_detail"]
CLOUD_COST_QUERY_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class CloudCostQueryPlan:
    kind: ReportKind
    bill_permission_map: dict
    log_permission_map: dict
    inst_type: str | None = None
    user_department: str | None = None
    applying_user: str | None = None
    billing_period: tuple[date, date] | None = None
    group_field: str | None = None
    page: int = 1
    page_size: int = 20
    sort_field: str = "total_cost_incurred"
    sort_order: str = "desc"


@dataclass(frozen=True)
class CompiledCloudCostQuery:
    statement: str
    params: dict[str, Any]


class _Params:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {
            "bill_model": "resource_bill",
            "log_model": "transaction_log",
        }
        self._index = 0

    def add(self, prefix: str, value: Any) -> str:
        self._index += 1
        name = f"{prefix}_{self._index}"
        self.values[name] = value
        return f"${name}"


_GROUP_FIELDS = {
    "object_type",
    "user_department",
    "applicant",
}

_SORT_EXPRESSIONS = {
    "total_cost_incurred": "total_cost",
    "instance_name": "instance_name",
    "department": "department",
}


def _stable_bill_key(alias: str = "bill") -> str:
    return (
        f"coalesce(toString({alias}.inst_uuid), "
        f"'object:' + toString({alias}.object_id), "
        f"'name:' + toString({alias}.inst_name))"
    )


def _permission_clause(
    *,
    alias: str,
    permission_map: dict,
    params: _Params,
    prefix: str,
) -> str:
    scopes = []
    organization_values = f"coalesce({alias}.organization, [])"
    for organization_id, permission_data in sorted(permission_map.items(), key=lambda item: str(item[0])):
        organization_param = params.add(f"{prefix}_org", [organization_id, str(organization_id)])
        parts = [f"ANY(scope_org IN {organization_param} WHERE scope_org IN {organization_values})"]
        inst_names = list((permission_data or {}).get("inst_names") or [])
        if inst_names:
            inst_names_param = params.add(f"{prefix}_names", inst_names)
            parts.append(f"{alias}.inst_name IN {inst_names_param}")
        scopes.append(f"({' AND '.join(parts)})")
    return f"({' OR '.join(scopes)})" if scopes else "false"


def _base_query(plan: CloudCostQueryPlan, params: _Params) -> str:
    conditions = [
        "bill.model_id = $bill_model",
        "log.model_id = $log_model",
        _permission_clause(
            alias="bill",
            permission_map=plan.bill_permission_map,
            params=params,
            prefix="bill",
        ),
        _permission_clause(
            alias="log",
            permission_map=plan.log_permission_map,
            params=params,
            prefix="log",
        ),
    ]
    for field, value, prefix in (
        ("object_type", plan.inst_type, "inst_type"),
        ("user_department", plan.user_department, "department"),
        ("applicant", plan.applying_user, "applicant"),
    ):
        if value:
            value_param = params.add(prefix, value)
            conditions.append(f"toLower(coalesce(bill.{field}, '')) CONTAINS toLower({value_param})")
    if plan.billing_period:
        start, end = plan.billing_period
        conditions.extend(
            [
                f"log.billing_date >= {params.add('billing_start', start.isoformat())}",
                f"log.billing_date <= {params.add('billing_end', end.isoformat())}",
            ]
        )
    return (
        f"MATCH (bill:{INSTANCE})-[:{INSTANCE_ASSOCIATION}]-(log:{INSTANCE})\n"
        f"WHERE {' AND '.join(conditions)}\n"
        "WITH DISTINCT bill, log"
    )


def _compile_summary(plan: CloudCostQueryPlan) -> CompiledCloudCostQuery:
    params = _Params()
    statement = (
        f"{_base_query(plan, params)}\n"
        "RETURN coalesce(sum(toFloat(log.total_cost)), 0.0) AS total_cost,\n"
        "       count(DISTINCT coalesce(toString(log.object_id), '__missing_object__')) AS instance_count,\n"
        "       min(log.billing_date) AS min_billing_date,\n"
        "       max(log.billing_date) AS max_billing_date"
    )
    return CompiledCloudCostQuery(statement=statement, params=params.values)


def _compile_distribution(plan: CloudCostQueryPlan) -> CompiledCloudCostQuery:
    if plan.group_field not in _GROUP_FIELDS:
        raise ValueError(f"unsupported cloud cost group field: {plan.group_field}")
    params = _Params()
    group_field = plan.group_field
    bill_key = _stable_bill_key()
    statement = (
        f"{_base_query(plan, params)}\n"
        f"WITH bill.{group_field} AS group_key, bill, log\n"
        "WHERE group_key IS NOT NULL\n"
        "WITH group_key,\n"
        "     coalesce(sum(toFloat(log.total_cost)), 0.0) AS total_cost,\n"
        f"     count(DISTINCT coalesce(toString(bill.object_id), 'bill:' + {bill_key})) AS instance_count\n"
        "RETURN toString(group_key) AS key, total_cost, instance_count\n"
        "ORDER BY total_cost DESC, key ASC"
    )
    return CompiledCloudCostQuery(statement=statement, params=params.values)


def _compile_bill_detail(plan: CloudCostQueryPlan) -> CompiledCloudCostQuery:
    sort_expression = _SORT_EXPRESSIONS.get(plan.sort_field)
    if not sort_expression:
        raise ValueError(f"unsupported cloud cost sort field: {plan.sort_field}")
    order = str(plan.sort_order or "desc").lower()
    if order not in {"asc", "desc"}:
        raise ValueError(f"unsupported cloud cost sort order: {plan.sort_order}")

    page = max(1, int(plan.page))
    page_size = max(1, int(plan.page_size))
    params = _Params()
    params.values.update(skip=(page - 1) * page_size, end=page * page_size)
    bill_key = _stable_bill_key()
    statement = (
        f"{_base_query(plan, params)}\n"
        "WITH bill,\n"
        "     coalesce(sum(toFloat(log.total_cost)), 0.0) AS total_cost,\n"
        "     min(log.billing_date) AS min_billing_date,\n"
        "     max(log.billing_date) AS max_billing_date\n"
        "WHERE total_cost <> 0\n"
        f"WITH {{bill_key: {bill_key}, object_id: coalesce(bill.object_id, ''),\n"
        "      instance_name: coalesce(bill.inst_name, ''), object_type: coalesce(bill.object_type, ''),\n"
        "      object_name: coalesce(bill.object_name, ''), department: coalesce(bill.user_department, ''),\n"
        "      user: coalesce(bill.applicant, ''), total_cost: total_cost,\n"
        "      min_billing_date: min_billing_date, max_billing_date: max_billing_date} AS item\n"
        f"ORDER BY item.{sort_expression} {order.upper()}, item.bill_key ASC\n"
        "WITH collect(item) AS items\n"
        "RETURN size(items) AS total, items[$skip..$end] AS items"
    )
    return CompiledCloudCostQuery(statement=statement, params=params.values)


def compile_cloud_cost_query(plan: CloudCostQueryPlan) -> CompiledCloudCostQuery:
    if plan.kind == "summary":
        return _compile_summary(plan)
    if plan.kind == "distribution":
        return _compile_distribution(plan)
    if plan.kind == "bill_detail":
        return _compile_bill_detail(plan)
    raise ValueError(f"unsupported cloud cost report kind: {plan.kind}")
