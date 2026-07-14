# -*- coding: utf-8 -*-
"""CloudCostService.summary 单元测试。

设计要点(2026-07-10 修订):
- instance_count:窗口内 log 按 object_id 去重的数量;空窗口 → 0。
- avg_daily_cost:
  - 有 billing_period → 日历天数 (end-start).days+1
  - 无 billing_period → 窗口内 log 的最早~最晚 billing_date 跨度天数
  - 无 log → 0(防除零)
- 不再返回 currency。
"""
from datetime import date
from decimal import Decimal

from apps.cmdb.services.cloud_cost.service import CloudCostService


def test_summary_empty_period_returns_zero(stub_orm):
    """空窗口:total/avg/instance_count 全 0,mom None;不再含 currency。"""
    result = CloudCostService.summary(
        stub_orm["user_info"], billing_period=(date(2030, 1, 1), date(2030, 1, 31))
    )
    assert result["total_cost"] == Decimal("0.00")
    assert result["instance_count"] == 0  # 窗口内 log=0 → 实例数=0
    assert result["avg_daily_cost"] == Decimal("0.00")
    assert result["mom_change_pct"] is None
    assert "currency" not in result


def test_summary_department_filter(stub_orm):
    """研发部 2 个不同 object_id → instance_count=2。"""
    result = CloudCostService.summary(stub_orm["user_info"], user_department="研发部")
    # 研发部 2 条 bill × 3 log × 100 = 600
    assert result["total_cost"] == Decimal("600.00")
    assert result["instance_count"] == 2


def test_summary_total_all(stub_orm):
    """无时间区间:total=1200,instance_count=4(4 个不同 object_id),
    avg_daily_cost = 1200 / (06-15 - 04-15 + 1) = 1200 / 62。"""
    result = CloudCostService.summary(stub_orm["user_info"])
    assert result["total_cost"] == Decimal("1200.00")
    assert result["instance_count"] == 4
    # 跨度:date(2026,6,15) - date(2026,4,15) = 61 天,闭区间 +1 = 62 天
    assert result["avg_daily_cost"] == (Decimal("1200") / Decimal("62")).quantize(Decimal("0.01"))
    assert result["mom_change_pct"] is None  # 无 billing_period → 不算 mom


def test_summary_mom_zero_when_equal(stub_orm):
    # 本期 2026-06(30 天)→ 4 条 log = 400;上期平移 30 天 = 2026-05-02~05-31 → 05-15 命中 4 条 = 400
    result = CloudCostService.summary(
        stub_orm["user_info"], billing_period=(date(2026, 6, 1), date(2026, 6, 30))
    )
    assert result["total_cost"] == Decimal("400.00")
    assert result["mom_change_pct"] == Decimal("0.0")


def test_summary_mom_null_when_prev_empty(stub_orm):
    # 本期 2030-06 无数据 → total 0 → mom None(不抛 ZeroDivisionError)
    result = CloudCostService.summary(
        stub_orm["user_info"], billing_period=(date(2030, 6, 1), date(2030, 6, 30))
    )
    assert result["total_cost"] == Decimal("0.00")
    assert result["mom_change_pct"] is None


def test_summary_avg_daily(stub_orm):
    # 2026-06 单月:total 400 / 30 天 = 13.33
    result = CloudCostService.summary(
        stub_orm["user_info"], billing_period=(date(2026, 6, 1), date(2026, 6, 30))
    )
    assert result["avg_daily_cost"] == Decimal("13.33")


def test_summary_avg_daily_no_period_uses_log_span(monkeypatch, stub_orm):
    """无 billing_period 时,avg_daily 分母 = log 跨度。

    stub_orm 默认数据跨度 04-15~06-15(62 天),这里替换为单条 log 跨度=1,
    验证 avg = total / 1。
    """
    from apps.cmdb.services.cloud_cost import orm
    USER_INFO = {"team": 1, "user": "tester"}

    single_log = [{
        "_id": 999, "_bill_id": 1, "object_id": "1",
        "billing_date": "2026-04-15", "total_cost": "50.00",
    }]

    def fake_logs(user_info, **kwargs):
        return single_log, len(single_log)

    monkeypatch.setattr(orm, "query_logs_by_filter", fake_logs)
    # query_bills_by_filter 仍走 stub_orm 的实现,但本测试不再依赖它
    result = CloudCostService.summary(USER_INFO)
    assert result["total_cost"] == Decimal("50.00")
    assert result["instance_count"] == 1
    # 跨度 = 1 天 → avg = 50 / 1 = 50.00
    assert result["avg_daily_cost"] == Decimal("50.00")


def test_summary_instance_count_dedups_by_object_id(monkeypatch):
    """同一资源实例(object_id)被拆成多张 bill,instance_count 应去重为 1。"""
    from apps.cmdb.services.cloud_cost import orm
    from apps.cmdb.services.cloud_cost.service import CloudCostService
    USER_INFO = {"team": 1, "user": "tester"}

    # 2 张 bill 共享同一 object_id(模拟"同一资源、按不同周期拆账")
    bills = [
        {"_id": 10, "inst_name": "shared-1", "object_type": "database", "object_name": "x",
         "user_department": "研发部", "applicant": "alice", "resource_unit_price": "30.00",
         "object_id": "shared-res"},
        {"_id": 11, "inst_name": "shared-2", "object_type": "database", "object_name": "x",
         "user_department": "研发部", "applicant": "alice", "resource_unit_price": "30.00",
         "object_id": "shared-res"},
    ]
    logs = [
        {"_id": 1001, "_bill_id": 10, "object_id": "shared-res",
         "billing_date": "2026-05-15", "total_cost": "100.00"},
        {"_id": 1002, "_bill_id": 11, "object_id": "shared-res",
         "billing_date": "2026-06-15", "total_cost": "200.00"},
    ]

    def fake_bills(user_info, **kwargs):
        return bills, len(bills)

    def fake_logs(user_info, **kwargs):
        return logs, len(logs)

    monkeypatch.setattr(orm, "query_bills_by_filter", fake_bills)
    monkeypatch.setattr(orm, "query_logs_by_filter", fake_logs)

    result = CloudCostService.summary(USER_INFO)
    assert result["total_cost"] == Decimal("300.00")
    assert result["instance_count"] == 1  # 2 张 bill,1 个 object_id → 1
