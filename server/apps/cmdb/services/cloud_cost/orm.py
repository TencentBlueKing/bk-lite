"""云成本报表的权限感知图查询入口。"""

from __future__ import annotations

from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.services.cloud_cost.query import CloudCostQueryPlan

RESOURCE_BILL_MODEL = "resource_bill"
TRANSACTION_LOG_MODEL = "transaction_log"


def _perm(user_info: dict, model_id: str):
    """生成报表图查询使用的实例权限；身份不完整时 fail-closed。"""
    from apps.cmdb.constants.constants import PERMISSION_INSTANCES
    from apps.cmdb.nats.nats import _build_nats_permission_map

    return _build_nats_permission_map(
        user_info or {},
        model_id=model_id,
        permission_type=PERMISSION_INSTANCES,
    )


def _permissions(user_info: dict) -> tuple[dict | None, dict | None]:
    return (
        _perm(user_info, RESOURCE_BILL_MODEL),
        _perm(user_info, TRANSACTION_LOG_MODEL),
    )


def _execute(plan: CloudCostQueryPlan) -> list[dict]:
    with GraphClient() as graph:
        return graph.query_cloud_cost(plan)


def query_summary(
    user_info: dict,
    *,
    inst_type=None,
    user_department=None,
    applying_user=None,
    billing_period=None,
) -> dict:
    bill_permission, log_permission = _permissions(user_info)
    if bill_permission is None or log_permission is None:
        return {}
    rows = _execute(
        CloudCostQueryPlan(
            kind="summary",
            bill_permission_map=bill_permission,
            log_permission_map=log_permission,
            inst_type=inst_type,
            user_department=user_department,
            applying_user=applying_user,
            billing_period=billing_period,
        )
    )
    return rows[0] if rows else {}


def query_distribution(
    user_info: dict,
    *,
    inst_type=None,
    user_department=None,
    applying_user=None,
    billing_period=None,
    group_field: str,
) -> list[dict]:
    bill_permission, log_permission = _permissions(user_info)
    if bill_permission is None or log_permission is None:
        return []
    return _execute(
        CloudCostQueryPlan(
            kind="distribution",
            bill_permission_map=bill_permission,
            log_permission_map=log_permission,
            inst_type=inst_type,
            user_department=user_department,
            applying_user=applying_user,
            billing_period=billing_period,
            group_field=group_field,
        )
    )


def query_bill_detail(
    user_info: dict,
    *,
    inst_type=None,
    user_department=None,
    applying_user=None,
    billing_period=None,
    page=1,
    page_size=20,
    sort_field="total_cost_incurred",
    sort_order="desc",
) -> dict:
    bill_permission, log_permission = _permissions(user_info)
    if bill_permission is None or log_permission is None:
        return {"total": 0, "items": []}
    rows = _execute(
        CloudCostQueryPlan(
            kind="bill_detail",
            bill_permission_map=bill_permission,
            log_permission_map=log_permission,
            inst_type=inst_type,
            user_department=user_department,
            applying_user=applying_user,
            billing_period=billing_period,
            page=page,
            page_size=page_size,
            sort_field=sort_field,
            sort_order=sort_order,
        )
    )
    return rows[0] if rows else {"total": 0, "items": []}
