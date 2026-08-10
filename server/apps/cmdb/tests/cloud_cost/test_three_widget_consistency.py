# -*- coding: utf-8 -*-
"""三 widget 一致性集成测试。

硬约束:summary.total_cost == sum(distribution[].total_cost) == sum(instance_list.items[].total_cost_incurred)
三者从同一份流水集合(stub_orm)算出。
"""
from decimal import Decimal

from apps.cmdb.services.cloud_cost.service import CloudCostService


def _consistent(user_info, **kw):
    s = CloudCostService.summary(user_info, **kw)
    d = CloudCostService.distribution(user_info, group_by="instance_type", **kw)
    il = CloudCostService.instance_list(user_info, page_size=1000, **kw)
    s_total = s["total_cost"]
    d_total = sum(
        (Decimal(str(row["total_cost"])) for row in d),
        Decimal("0"),
    )
    i_total = sum((i["total_cost_incurred"] for i in il["items"]), Decimal("0"))
    assert abs(s_total - d_total) < Decimal("0.01"), f"summary={s_total} vs distribution={d_total}"
    assert abs(s_total - i_total) < Decimal("0.01"), f"summary={s_total} vs instance_list={i_total}"


def test_consistency_no_filter(stub_orm):
    _consistent(stub_orm["user_info"])


def test_consistency_by_department(stub_orm):
    for dept in ("研发部", "运维部", "测试部"):
        _consistent(stub_orm["user_info"], user_department=dept)
