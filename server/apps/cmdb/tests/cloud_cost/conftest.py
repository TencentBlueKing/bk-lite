# -*- coding: utf-8 -*-
"""cloud_cost service 层测试夹具。

不写真实 DB/图(图写不回滚会污染 cmdb_graph),改为:
- 内存数据集(4 bill × 每 bill 3 log,字段名对齐真实环境)
- stub_orm fixture:monkeypatch orm.query_bills_by_filter / query_logs_by_filter
  按筛选参数过滤内存数据集,让 service 聚合逻辑跑在真实形状的数据上。
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
    """把 service 依赖的 orm 两个查询函数换成内存实现。"""
    from apps.cmdb.services.cloud_cost import orm

    def fake_bills(user_info, *, inst_type=None, user_department=None,
                   applying_user=None, billing_period=None):
        bills = [b for b in BILLS if _match_bill(b, inst_type, user_department, applying_user)]
        return bills, len(bills)

    def fake_logs(user_info, *, inst_type=None, user_department=None,
                  applying_user=None, billing_period=None):
        eligible = {b["_id"] for b in BILLS if _match_bill(b, inst_type, user_department, applying_user)}
        logs = [dict(lg) for lg in LOGS if lg["_bill_id"] in eligible and _in_period(lg, billing_period)]
        return logs, len(logs)

    monkeypatch.setattr(orm, "query_bills_by_filter", fake_bills)
    monkeypatch.setattr(orm, "query_logs_by_filter", fake_logs)
    return {"user_info": USER_INFO, "bills": BILLS, "logs": LOGS}
