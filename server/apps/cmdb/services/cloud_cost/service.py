# -*- coding: utf-8 -*-
"""
云资源成本分析 Service 层。

3 个 widget 共用同一权限感知的图查询语义,确保:
  summary.total_cost == sum(distribution[].total_cost) == sum(instance_list.items.total_cost_incurred)

字段名对齐 2026-07-10 真实环境实测:
  bill: object_type / user_department / applicant / object_name / resource_unit_price
  log:  billing_date / total_cost
"""
from datetime import date, timedelta
from decimal import Decimal

from apps.cmdb.services.cloud_cost import orm

_TWO = Decimal("0.01")
_ONE = Decimal("0.1")
_MAX_DETAIL_PAGE_SIZE = 1000


def _to_decimal(value) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _span_days(start, end) -> int:
    """两个 ISO 日期之间的闭区间天数；缺失或非法值返回 0。"""
    if not start or not end:
        return 0
    try:
        return (date.fromisoformat(str(end)) - date.fromisoformat(str(start))).days + 1
    except (TypeError, ValueError):
        return 0


class CloudCostService:
    """云资源成本分析业务聚合服务。"""

    @staticmethod
    def _shift_period(period, days):
        start, end = period
        delta = timedelta(days=days)
        return start - delta, end - delta

    @staticmethod
    def _compute_mom_pct(current: Decimal, previous: Decimal):
        """同环比;边界(任一为 0)全部返回 None,禁止抛异常。"""
        if previous == 0 or current == 0:
            return None
        return ((current - previous) / previous * Decimal("100")).quantize(_ONE)

    @staticmethod
    def summary(user_info, *, inst_type=None, user_department=None,
                applying_user=None, billing_period=None):
        """
        KPI 汇总卡。

        口径(2026-07-10 修订):
          - instance_count: 窗口内 log 按 object_id 去重;空窗口 → 0。
            同资源多张 bill(不同周期)共享 object_id,自动合并计数。
          - avg_daily_cost: 有 billing_period → 日历天数;无 → log 跨度天数;空 → 0。
          - 不再返回 currency。

        Returns:
            {
                "total_cost": Decimal,            # 区间内 total_cost SUM
                "instance_count": int,            # 窗口内 DISTINCT log.object_id
                "avg_daily_cost": Decimal,        # total_cost / 分母天数
                "mom_change_pct": Decimal | None, # 同环比(±0.1)
            }
        """
        current = orm.query_summary(
            user_info, inst_type=inst_type, user_department=user_department,
            applying_user=applying_user, billing_period=billing_period,
        )
        total_cost = _to_decimal(current.get("total_cost"))
        instance_count = int(current.get("instance_count") or 0)

        if billing_period:
            days = (billing_period[1] - billing_period[0]).days + 1
        else:
            days = _span_days(current.get("min_billing_date"), current.get("max_billing_date"))
        avg_daily = (total_cost / Decimal(days)).quantize(_TWO) if days > 0 else Decimal("0")

        mom_pct = None
        if billing_period:
            prev_period = CloudCostService._shift_period(billing_period, days)
            previous = orm.query_summary(
                user_info, inst_type=inst_type, user_department=user_department,
                applying_user=applying_user, billing_period=prev_period,
            )
            mom_pct = CloudCostService._compute_mom_pct(total_cost, _to_decimal(previous.get("total_cost")))

        return {
            "total_cost": total_cost.quantize(_TWO),
            "instance_count": instance_count,
            "avg_daily_cost": avg_daily,
            "mom_change_pct": mom_pct,
        }

    # group_by 值 → bill 上的真实字段
    _GROUP_FIELD = {
        "instance_type": "object_type",
        "department": "user_department",
        "user": "applicant",
    }

    @staticmethod
    def distribution(user_info, *, inst_type=None, user_department=None,
                     applying_user=None, billing_period=None, group_by="instance_type"):
        """
        费用分布图。

        Args:
            group_by: instance_type(→object_type) | department(→user_department) | user(→applicant)

        Returns:
            [{"key": str, "total_cost": float,
              "instance_count": int, "pct": float}]
        """
        field = CloudCostService._GROUP_FIELD.get(group_by)
        if field is None:
            raise ValueError(f"unsupported group_by: {group_by}")

        rows = orm.query_distribution(
            user_info, inst_type=inst_type, user_department=user_department,
            applying_user=applying_user, billing_period=billing_period,
            group_field=field,
        )
        grand_total = sum((_to_decimal(row.get("total_cost")) for row in rows), Decimal("0"))
        groups = []
        for row in rows:
            key = row.get("key")
            total = _to_decimal(row.get("total_cost"))
            pct = (total / grand_total * Decimal("100")).quantize(_TWO) if grand_total else Decimal("0")
            groups.append({
                "key": str(key),
                "total_cost": float(total.quantize(_TWO)),
                "instance_count": int(row.get("instance_count") or 0),
                "pct": float(pct),
            })
        groups.sort(key=lambda row: row["total_cost"], reverse=True)
        return groups

    _SORT_FIELDS = frozenset({"total_cost_incurred", "instance_name", "department"})

    @staticmethod
    def instance_list(user_info, *, inst_type=None, user_department=None,
                      applying_user=None, billing_period=None,
                      page=1, page_size=20, sort_by="total_cost_incurred", order="desc"):
        """
        资源账单明细表。

        行粒度 = 一张 bill(同资源多张 bill 不合并)。
        8 列字段:object_id / instance_name / object_type / object_name /
                 department / user / total_cost_incurred / unit_price

        口径(2026-07-10 修订):
          - total_cost_incurred = 此 bill 在窗口内的 SUM(log.total_cost)
            不是 bill.total_accrued_expenses(那是整段周期固定值)。
          - unit_price = total_cost_incurred / days(从 log 算,不是 bill.resource_unit_price)
            · 有 billing_period → 日历天数 (end-start).days+1
            · 无 billing_period → 此 bill 自己的 log 最早~最晚 billing_date 跨度天数
          - object_id = bill.object_id(资源实例 id;真实 schema 里 bill 自带此字段,
            直接读即可,不从 log 反查)
          - 筛选条件下(含 billing_period)log=0 的 bill 不入表;
            cost 累加为 0 的 bill(有 log 但 total_cost=0)同样不入表
          - 删除 cost_pct 字段
          - 字段名:inst_id→object_id, instance_type→object_type,
            total_cost→total_cost_incurred

        聚合、稳定排序、精确总数和页切片由一次图查询完成；
        service 只做金额与展示字段格式化。

        Returns:
            {"total": int, "page": int, "page_size": int, "items": [...]}
        """
        page = int(page)
        page_size = int(page_size)
        if page < 1:
            raise ValueError("page must be >= 1")
        if page_size < 1 or page_size > _MAX_DETAIL_PAGE_SIZE:
            raise ValueError(f"page_size must be between 1 and {_MAX_DETAIL_PAGE_SIZE}")
        sort_by = sort_by if sort_by in CloudCostService._SORT_FIELDS else "total_cost_incurred"
        order = "desc" if order == "desc" else "asc"
        result = orm.query_bill_detail(
            user_info, inst_type=inst_type, user_department=user_department,
            applying_user=applying_user, billing_period=billing_period,
            page=page, page_size=page_size, sort_field=sort_by, sort_order=order,
        )
        items = []
        for row in result.get("items") or []:
            cost = _to_decimal(row.get("total_cost"))
            if billing_period:
                days = (billing_period[1] - billing_period[0]).days + 1
            else:
                days = _span_days(row.get("min_billing_date"), row.get("max_billing_date"))
            unit_price = (cost / Decimal(days)).quantize(_TWO) if days > 0 else Decimal("0")

            items.append({
                "object_id": row.get("object_id", ""),
                "instance_name": row.get("instance_name", ""),
                "object_type": row.get("object_type", ""),
                "object_name": row.get("object_name", ""),
                "department": row.get("department", ""),
                "user": row.get("user", ""),
                "total_cost_incurred": cost.quantize(_TWO),
                "unit_price": unit_price,
            })
        return {
            "total": int(result.get("total") or 0),
            "page": page,
            "page_size": page_size,
            "items": items,
        }
