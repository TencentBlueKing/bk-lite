# -*- coding: utf-8 -*-
"""
云资源成本分析 Service 层。

3 个 widget 共用同一份流水集合(由 orm 层提供),确保:
  summary.total_cost == sum(distribution[].total_cost) == sum(instance_list.items.total_cost_incurred)

字段名对齐 2026-07-10 真实环境实测:
  bill: object_type / user_department / applicant / object_name / resource_unit_price
  log:  billing_date / total_cost(+ orm 反哺的 _bill_id)
"""
from datetime import date, timedelta
from decimal import Decimal

from apps.cmdb.services.cloud_cost import orm

_TWO = Decimal("0.01")
_ONE = Decimal("0.1")


def _to_decimal(value) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _sum_cost(logs) -> Decimal:
    return sum((_to_decimal(lg.get("total_cost")) for lg in logs), Decimal("0"))


def _log_span_days(logs) -> int:
    """窗口内 log 的最早~最晚 billing_date 跨度天数(闭区间)。空集 → 0。"""
    if not logs:
        return 0
    dates = [date.fromisoformat(lg["billing_date"]) for lg in logs]
    return (max(dates) - min(dates)).days + 1


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
        current_logs, _ = orm.query_logs_by_filter(
            user_info, inst_type=inst_type, user_department=user_department,
            applying_user=applying_user, billing_period=billing_period,
        )
        total_cost = _sum_cost(current_logs)
        instance_count = len({lg.get("object_id") for lg in current_logs})

        if billing_period:
            days = (billing_period[1] - billing_period[0]).days + 1
        else:
            days = _log_span_days(current_logs)
        avg_daily = (total_cost / Decimal(days)).quantize(_TWO) if days > 0 else Decimal("0")

        mom_pct = None
        if billing_period:
            prev_period = CloudCostService._shift_period(billing_period, days)
            prev_logs, _ = orm.query_logs_by_filter(
                user_info, inst_type=inst_type, user_department=user_department,
                applying_user=applying_user, billing_period=prev_period,
            )
            mom_pct = CloudCostService._compute_mom_pct(total_cost, _sum_cost(prev_logs))

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

        logs, _ = orm.query_logs_by_filter(
            user_info, inst_type=inst_type, user_department=user_department,
            applying_user=applying_user, billing_period=billing_period,
        )
        bills, _ = orm.query_bills_by_filter(
            user_info, inst_type=inst_type, user_department=user_department,
            applying_user=applying_user,
        )
        bill_group = {b["_id"]: b.get(field) for b in bills}
        bill_instance = {
            b["_id"]: (
                b.get("object_id")
                if b.get("object_id") not in (None, "")
                else ("bill", b["_id"])
            )
            for b in bills
        }

        group_total = {}
        group_insts = {}
        for lg in logs:
            key = bill_group.get(lg.get("_bill_id"))
            if key is None:
                continue  # 关联丢失,跳过
            group_total[key] = group_total.get(key, Decimal("0")) + _to_decimal(lg.get("total_cost"))
            group_insts.setdefault(key, set()).add(bill_instance[lg.get("_bill_id")])

        grand_total = sum(group_total.values(), Decimal("0"))
        groups = []
        for key, total in group_total.items():
            pct = (total / grand_total * Decimal("100")).quantize(_TWO) if grand_total else Decimal("0")
            groups.append({
                "key": str(key),
                "total_cost": float(total.quantize(_TWO)),
                "instance_count": len(group_insts[key]),
                "pct": float(pct),
            })
        groups.sort(key=lambda row: row["total_cost"], reverse=True)
        return groups

    _SORT_KEY = {
        "total_cost_incurred": lambda i: i["total_cost_incurred"],
        "instance_name": lambda i: i["instance_name"],
        "department": lambda i: i["department"],
    }

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

        分页在 service 层做。

        Returns:
            {"total": int, "page": int, "page_size": int, "items": [...]}
        """
        logs, _ = orm.query_logs_by_filter(
            user_info, inst_type=inst_type, user_department=user_department,
            applying_user=applying_user, billing_period=billing_period,
        )
        bills, _ = orm.query_bills_by_filter(
            user_info, inst_type=inst_type, user_department=user_department,
            applying_user=applying_user,
        )

        # 按 bill 聚合:cost / log 日期(用于无窗口时算单价分母)
        # object_id 直接从 bill 读(不再从 log 反查),真实 schema 里 bill 自带此字段。
        bill_cost = {}        # bill_id → Decimal
        bill_log_dates = {}   # bill_id → list[date]
        for lg in logs:
            bid = lg.get("_bill_id")
            if bid is None:
                continue
            bill_cost[bid] = bill_cost.get(bid, Decimal("0")) + _to_decimal(lg.get("total_cost"))
            bill_log_dates.setdefault(bid, []).append(date.fromisoformat(lg["billing_date"]))

        items = []
        for b in bills:
            bid = b["_id"]
            cost = bill_cost.get(bid, Decimal("0"))
            if cost == 0:
                # 筛选条件下 log=0 的 bill 或 log 累加 cost=0 的 bill 都不入表
                continue

            # 单价分母:有窗口=日历天数;无窗口=此 bill 的 log 跨度天数
            if billing_period:
                days = (billing_period[1] - billing_period[0]).days + 1
            else:
                dates = bill_log_dates.get(bid, [])
                days = (max(dates) - min(dates)).days + 1 if dates else 0
            unit_price = (cost / Decimal(days)).quantize(_TWO) if days > 0 else Decimal("0")

            items.append({
                "object_id": b.get("object_id", ""),
                "instance_name": b.get("inst_name", ""),
                "object_type": b.get("object_type", ""),
                "object_name": b.get("object_name", ""),
                "department": b.get("user_department", ""),
                "user": b.get("applicant", ""),
                "total_cost_incurred": cost.quantize(_TWO),
                "unit_price": unit_price,
            })

        sort_key = CloudCostService._SORT_KEY.get(
            sort_by, CloudCostService._SORT_KEY["total_cost_incurred"]
        )
        items.sort(key=sort_key, reverse=(order == "desc"))

        total = len(items)
        start = (page - 1) * page_size
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": items[start:start + page_size],
        }
