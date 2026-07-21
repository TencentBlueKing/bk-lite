# -*- coding: utf-8 -*-
"""CloudCostService.instance_list(资源账单明细)单元测试。

设计要点(2026-07-10 修订):
- 行粒度 = 一张 bill(同资源多张 bill 不合并)
- 8 列字段:object_id / instance_name / object_type / object_name /
  department / user / total_cost_incurred / unit_price
- total_cost_incurred = SUM(此 bill 在窗口内的 log.total_cost)
- unit_price = total_cost_incurred / days
  · 有 billing_period → 日历天数
  · 无 billing_period → 此 bill 自己的 log 最早~最晚 billing_date 跨度天数
- object_id = bill.object_id(资源实例 id;真实 schema 里 bill 自带此字段,直接读)
- 0 花费 bill(窗口内)不入表
- 删除 cost_pct 字段
- 字段名:inst_id→object_id, instance_type→object_type, total_cost→total_cost_incurred
"""
from datetime import date
from decimal import Decimal

from apps.cmdb.services.cloud_cost.service import CloudCostService


def test_instance_list_default_sort_desc(stub_orm):
    """默认按 total_cost_incurred DESC 排序。"""
    result = CloudCostService.instance_list(stub_orm["user_info"])
    costs = [i["total_cost_incurred"] for i in result["items"]]
    assert costs == sorted(costs, reverse=True)
    assert result["total"] == 4


def test_instance_list_fields_mapped(stub_orm):
    """字段映射:object_type←bill.object_type,user←bill.applicant,department←bill.user_department。
    object_id 直接读 bill.object_id(资源实例 id)。
    """
    result = CloudCostService.instance_list(
        stub_orm["user_info"], user_department="研发部"
    )
    assert result["total"] == 2
    item = result["items"][0]
    # 8 个返回字段
    assert item["object_type"] == "database"
    assert item["department"] == "研发部"
    assert item["user"] == "alice"
    # total_cost_incurred = 3 log × 100 = 300
    assert item["total_cost_incurred"] == Decimal("300.00")
    # object_id 直接读 bill.object_id(conftest 里是 res-1 / res-2)
    assert item["object_id"] in ("res-1", "res-2")
    # cost_pct 已删除
    assert "cost_pct" not in item
    # 老字段名已删除
    assert "inst_id" not in item
    assert "instance_type" not in item
    assert "total_cost" not in item


def test_instance_list_pagination(stub_orm):
    """分页:用 object_id 作为唯一 key。"""
    p1 = CloudCostService.instance_list(stub_orm["user_info"], page=1, page_size=2)
    p2 = CloudCostService.instance_list(stub_orm["user_info"], page=2, page_size=2)
    assert len(p1["items"]) == 2
    assert len(p2["items"]) == 2
    ids1 = {i["object_id"] for i in p1["items"]}
    ids2 = {i["object_id"] for i in p2["items"]}
    assert ids1.isdisjoint(ids2)
    assert result_total(stub_orm) == 4


def _result_total(stub_orm):
    return CloudCostService.instance_list(
        stub_orm["user_info"], page_size=1000
    )["total"]


def result_total(stub_orm):  # helper exposed to module
    return _result_total(stub_orm)


def test_instance_list_department_filter(stub_orm):
    result = CloudCostService.instance_list(
        stub_orm["user_info"], user_department="研发部"
    )
    assert all(i["department"] == "研发部" for i in result["items"])
    assert result["total"] == 2


def test_instance_list_unit_price_with_window(stub_orm):
    """有 billing_period:unit_price = total_cost_incurred / 日历天数。

    研发部 2 bills,每 bill 在 2026-06 窗口内只有 1 条 log(cost=100);
    日历天数 = 30;unit_price = 100/30 = 3.33 元/天/bill。
    """
    result = CloudCostService.instance_list(
        stub_orm["user_info"],
        user_department="研发部",
        billing_period=(date(2026, 6, 1), date(2026, 6, 30)),
    )
    assert result["total"] == 2
    for item in result["items"]:
        assert item["total_cost_incurred"] == Decimal("100.00")
        assert item["unit_price"] == (Decimal("100") / Decimal("30")).quantize(Decimal("0.01"))


def test_instance_list_unit_price_without_window_uses_bill_log_span(stub_orm):
    """无 billing_period:unit_price = total / 此 bill 的 log 跨度天数。

    研发部 2 bills,每 bill 有 04-15 / 05-15 / 06-15 三条 log,
    跨度 = (06-15 - 04-15).days + 1 = 62 天。
    total = 300,unit_price = 300/62 = 4.84 元/天/bill。
    """
    result = CloudCostService.instance_list(
        stub_orm["user_info"], user_department="研发部"
    )
    for item in result["items"]:
        assert item["total_cost_incurred"] == Decimal("300.00")
        assert item["unit_price"] == (Decimal("300") / Decimal("62")).quantize(Decimal("0.01"))


def test_instance_list_unit_price_zero_when_no_logs(stub_orm):
    """窗口内 0 条 log 的 bill 不入表(被 P2-1 跳过),不会触发除零。"""
    result = CloudCostService.instance_list(
        stub_orm["user_info"],
        billing_period=(date(2030, 1, 1), date(2030, 1, 31)),
    )
    assert result["total"] == 0
    assert result["items"] == []


def test_instance_list_object_id_from_bill(stub_orm):
    """object_id 字段直接读 bill.object_id(conftest 里是 res-1..res-4)。"""
    result = CloudCostService.instance_list(stub_orm["user_info"])
    object_ids = {i["object_id"] for i in result["items"]}
    assert object_ids == {"res-1", "res-2", "res-3", "res-4"}


def test_instance_list_object_id_uses_bill_not_log(monkeypatch):
    """脏数据兜底:同 bill 的 log 上 object_id 不一致时,返回 bill 上的 object_id(不会乱跳)。"""
    from apps.cmdb.services.cloud_cost import orm
    from apps.cmdb.services.cloud_cost.service import CloudCostService
    USER_INFO = {"team": 1, "user": "tester"}

    bills = [
        {"_id": 10, "inst_name": "x", "object_type": "compute",
         "object_name": "x", "user_department": "研发部", "applicant": "alice",
         "resource_unit_price": "30.00", "object_id": "canonical"},
    ]
    # log 上 3 条 object_id 都不一样(模拟脏数据:采集/合并遗留)
    logs = [
        {"_id": 1001, "_bill_id": 10, "object_id": "log-junk-1",
         "billing_date": "2026-04-15", "total_cost": "100.00"},
        {"_id": 1002, "_bill_id": 10, "object_id": "log-junk-2",
         "billing_date": "2026-05-15", "total_cost": "100.00"},
        {"_id": 1003, "_bill_id": 10, "object_id": "log-junk-3",
         "billing_date": "2026-06-15", "total_cost": "100.00"},
    ]

    monkeypatch.setattr(orm, "query_bills_by_filter",
                        lambda *a, **kw: (bills, len(bills)))
    monkeypatch.setattr(orm, "query_logs_by_filter",
                        lambda *a, **kw: (logs, len(logs)))

    result = CloudCostService.instance_list(USER_INFO)
    assert result["total"] == 1
    assert result["items"][0]["object_id"] == "canonical"


def test_instance_list_same_object_id_multiple_bills_not_merged(monkeypatch):
    """同 object_id 的 2 张 bill 不合并,各自成行,但 object_id 字段相同。"""
    from apps.cmdb.services.cloud_cost import orm
    from apps.cmdb.services.cloud_cost.service import CloudCostService
    USER_INFO = {"team": 1, "user": "tester"}

    bills = [
        {"_id": 10, "inst_name": "shared-1", "object_type": "database",
         "object_name": "x", "user_department": "研发部", "applicant": "alice",
         "resource_unit_price": "30.00", "object_id": "shared-res"},
        {"_id": 11, "inst_name": "shared-2", "object_type": "database",
         "object_name": "x", "user_department": "研发部", "applicant": "alice",
         "resource_unit_price": "30.00", "object_id": "shared-res"},
    ]
    logs = [
        {"_id": 1001, "_bill_id": 10, "object_id": "shared-res",
         "billing_date": "2026-05-15", "total_cost": "100.00"},
        {"_id": 1002, "_bill_id": 11, "object_id": "shared-res",
         "billing_date": "2026-06-15", "total_cost": "200.00"},
    ]

    monkeypatch.setattr(orm, "query_bills_by_filter",
                        lambda *a, **kw: (bills, len(bills)))
    monkeypatch.setattr(orm, "query_logs_by_filter",
                        lambda *a, **kw: (logs, len(logs)))

    result = CloudCostService.instance_list(USER_INFO)
    assert result["total"] == 2  # 不合并
    assert all(i["object_id"] == "shared-res" for i in result["items"])
    # 两张 bill 的 total_cost_incurred 不同
    costs = sorted(i["total_cost_incurred"] for i in result["items"])
    assert costs == [Decimal("100.00"), Decimal("200.00")]
