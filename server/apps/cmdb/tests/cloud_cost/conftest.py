# -*- coding: utf-8 -*-
"""cloud_cost service 层测试夹具。

不写真实 DB/图(图写不回滚会污染 cmdb_graph),改为:
- 内存数据集(4 bill × 每 bill 3 log,字段名对齐真实环境)
- stub_orm fixture:monkeypatch 三个权限感知聚合查询，按筛选参数过滤内存数据集，
  让 service 的金额、环比和展示格式逻辑跑在真实形状的数据上。
"""
from datetime import date

import pytest

USER_INFO = {"team": 1, "user": "tester"}

# 4 条 bill:研发部 2 条(database/alice),运维部 1 条(cache/bob),测试部 1 条(compute/charlie)
# 真实 schema(2026-07-10 实测):resource_bill 自带 object_id(资源实例 id),与所属 transaction_log 一一对应。
BILLS = [
    {"_id": 1, "inst_name": "prod-db-01", "object_type": "database", "object_name": "生产库1",
     "user_department": "研发部", "applicant": "alice", "resource_unit_price": "30.00",
     "object_id": "res-1"},
    {"_id": 2, "inst_name": "prod-db-02", "object_type": "database", "object_name": "生产库2",
     "user_department": "研发部", "applicant": "alice", "resource_unit_price": "30.00",
     "object_id": "res-2"},
    {"_id": 3, "inst_name": "ops-cache-01", "object_type": "cache", "object_name": "缓存1",
     "user_department": "运维部", "applicant": "bob", "resource_unit_price": "50.00",
     "object_id": "res-3"},
    {"_id": 4, "inst_name": "qa-vm-01", "object_type": "compute", "object_name": "测试机1",
     "user_department": "测试部", "applicant": "charlie", "resource_unit_price": "20.00",
     "object_id": "res-4"},
]

# 每条 bill 3 条 log:2026-04/05/06,每条 100.00
# transaction_log 也带 object_id(与所属 resource_bill.object_id 一致),这里保留以贴合真实 schema;
# 但 instance_list 的 object_id 字段直接读 bill,不再走 log。
LOGS = []
for _b in BILLS:
    for _m in ("04", "05", "06"):
        LOGS.append({
            "_id": _b["_id"] * 100 + int(_m),
            "_bill_id": _b["_id"],
            "object_id": _b["object_id"],
            "billing_date": f"2026-{_m}-15",
            "total_cost": "100.00",
        })


def _match_bill(bill, inst_type, user_department, applying_user):
    """三个 bill 维度筛选走「大小写不敏感子串匹配」,与 2026-07-14 改造后
    orm 层 str* + case_sensitive=False 在 FalkorDB 上的语义对齐。
    """
    if inst_type and inst_type.lower() not in (bill.get("object_type") or "").lower():
        return False
    if user_department and user_department.lower() not in (bill.get("user_department") or "").lower():
        return False
    if applying_user and applying_user.lower() not in (bill.get("applicant") or "").lower():
        return False
    return True


def _in_period(log, billing_period):
    if not billing_period:
        return True
    start, end = billing_period
    d = date.fromisoformat(log["billing_date"])
    return start <= d <= end


@pytest.fixture
def stub_orm(monkeypatch):
    """把 service 依赖的三种聚合查询换成内存实现。"""
    from apps.cmdb.services.cloud_cost import orm

    def selected(inst_type=None, user_department=None, applying_user=None, billing_period=None):
        bills = [b for b in BILLS if _match_bill(b, inst_type, user_department, applying_user)]
        eligible = {b["_id"] for b in bills}
        logs = [dict(lg) for lg in LOGS if lg["_bill_id"] in eligible and _in_period(lg, billing_period)]
        return bills, logs

    def fake_summary(user_info, *, inst_type=None, user_department=None,
                     applying_user=None, billing_period=None):
        _, logs = selected(inst_type, user_department, applying_user, billing_period)
        return {
            "total_cost": sum(float(log["total_cost"]) for log in logs),
            "instance_count": len({log.get("object_id") for log in logs}),
            "min_billing_date": min((log["billing_date"] for log in logs), default=None),
            "max_billing_date": max((log["billing_date"] for log in logs), default=None),
        }

    def fake_distribution(user_info, *, inst_type=None, user_department=None,
                          applying_user=None, billing_period=None, group_field=None):
        bills, logs = selected(inst_type, user_department, applying_user, billing_period)
        bills_by_id = {bill["_id"]: bill for bill in bills}
        rows = {}
        for log in logs:
            bill = bills_by_id[log["_bill_id"]]
            key = bill.get(group_field)
            row = rows.setdefault(key, {"key": key, "total_cost": 0.0, "objects": set()})
            row["total_cost"] += float(log["total_cost"])
            row["objects"].add(bill.get("object_id") or ("bill", bill["_id"]))
        return [
            {"key": row["key"], "total_cost": row["total_cost"], "instance_count": len(row["objects"])}
            for row in rows.values()
        ]

    def fake_detail(user_info, *, inst_type=None, user_department=None,
                    applying_user=None, billing_period=None, page=1, page_size=20,
                    sort_field="total_cost_incurred", sort_order="desc"):
        bills, logs = selected(inst_type, user_department, applying_user, billing_period)
        logs_by_bill = {}
        for log in logs:
            logs_by_bill.setdefault(log["_bill_id"], []).append(log)
        items = []
        for bill in bills:
            bill_logs = logs_by_bill.get(bill["_id"], [])
            cost = sum(float(log["total_cost"]) for log in bill_logs)
            if cost == 0:
                continue
            items.append({
                "bill_id": bill["_id"],
                "object_id": bill.get("object_id", ""),
                "instance_name": bill.get("inst_name", ""),
                "object_type": bill.get("object_type", ""),
                "object_name": bill.get("object_name", ""),
                "department": bill.get("user_department", ""),
                "user": bill.get("applicant", ""),
                "total_cost": cost,
                "min_billing_date": min((log["billing_date"] for log in bill_logs), default=None),
                "max_billing_date": max((log["billing_date"] for log in bill_logs), default=None),
            })
        sort_key = {
            "total_cost_incurred": "total_cost",
            "instance_name": "instance_name",
            "department": "department",
        }.get(sort_field, "total_cost")
        items.sort(key=lambda item: item["bill_id"])
        items.sort(key=lambda item: item[sort_key], reverse=(sort_order == "desc"))
        start = (page - 1) * page_size
        return {"total": len(items), "items": items[start:start + page_size]}

    monkeypatch.setattr(orm, "query_summary", fake_summary)
    monkeypatch.setattr(orm, "query_distribution", fake_distribution)
    monkeypatch.setattr(orm, "query_bill_detail", fake_detail)
    return {"user_info": USER_INFO, "bills": BILLS, "logs": LOGS}
