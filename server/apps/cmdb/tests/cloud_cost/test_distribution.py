# -*- coding: utf-8 -*-
"""CloudCostService.distribution 单元测试。"""
import pytest

from apps.cmdb.services.cloud_cost.service import CloudCostService


def _rows_by_key(result):
    assert isinstance(result, list)
    for row in result:
        assert set(row) == {"key", "total_cost", "instance_count", "pct"}
        assert type(row["key"]) is str
        assert type(row["total_cost"]) is float
        assert type(row["instance_count"]) is int
        assert type(row["pct"]) is float
    return {row["key"]: row for row in result}


def test_distribution_by_instance_type(stub_orm):
    result = CloudCostService.distribution(stub_orm["user_info"], group_by="instance_type")
    groups = _rows_by_key(result)
    # database 2 bill × 3 log × 100 = 600
    assert groups["database"]["total_cost"] == 600.0
    assert groups["database"]["instance_count"] == 2
    assert groups["cache"]["total_cost"] == 300.0
    assert groups["compute"]["total_cost"] == 300.0


def test_distribution_by_department(stub_orm):
    result = CloudCostService.distribution(stub_orm["user_info"], group_by="department")
    groups = _rows_by_key(result)
    assert groups["研发部"]["total_cost"] == 600.0
    assert groups["运维部"]["total_cost"] == 300.0
    assert groups["测试部"]["total_cost"] == 300.0


def test_distribution_by_user(stub_orm):
    result = CloudCostService.distribution(stub_orm["user_info"], group_by="user")
    groups = _rows_by_key(result)
    # alice 2 bill × 3 log × 100 = 600
    assert groups["alice"]["total_cost"] == 600.0
    assert groups["bob"]["total_cost"] == 300.0


def test_distribution_instance_count_deduplicates_object_across_bills(monkeypatch):
    from apps.cmdb.services.cloud_cost import orm

    bills = [
        {"_id": 1, "object_type": "database", "object_id": "shared-resource"},
        {"_id": 2, "object_type": "database", "object_id": "shared-resource"},
    ]
    logs = [
        {"_bill_id": 1, "object_id": "shared-resource", "total_cost": "10.00"},
        {"_bill_id": 2, "object_id": "shared-resource", "total_cost": "20.00"},
    ]
    monkeypatch.setattr(
        orm,
        "query_bills_by_filter",
        lambda *args, **kwargs: (bills, len(bills)),
    )
    monkeypatch.setattr(
        orm,
        "query_logs_by_filter",
        lambda *args, **kwargs: (logs, len(logs)),
    )

    groups = _rows_by_key(
        CloudCostService.distribution({"team": 1}, group_by="instance_type")
    )

    assert groups["database"]["total_cost"] == 30.0
    assert groups["database"]["instance_count"] == 1


def test_distribution_pct_sums_100(stub_orm):
    result = CloudCostService.distribution(stub_orm["user_info"], group_by="instance_type")
    total_pct = sum(row["pct"] for row in result)
    assert abs(total_pct - 100.0) < 0.01


def test_distribution_sorted_desc(stub_orm):
    result = CloudCostService.distribution(stub_orm["user_info"], group_by="instance_type")
    costs = [row["total_cost"] for row in result]
    assert costs == sorted(costs, reverse=True)


def test_distribution_invalid_group_by_raises(stub_orm):
    with pytest.raises(ValueError):
        CloudCostService.distribution(stub_orm["user_info"], group_by="bogus")


def test_nats_distribution_returns_standard_rows(monkeypatch):
    from apps.cmdb.nats.nats import get_cloud_resource_cost_distribution

    rows = [
        {
            "key": "database",
            "total_cost": 600.0,
            "instance_count": 2,
            "pct": 50.0,
        },
    ]
    monkeypatch.setattr(
        CloudCostService,
        "distribution",
        staticmethod(lambda *args, **kwargs: rows),
    )

    result = get_cloud_resource_cost_distribution(
        user_info={"team": 1},
        group_by="instance_type",
    )

    assert result == {"result": True, "data": rows, "message": ""}
