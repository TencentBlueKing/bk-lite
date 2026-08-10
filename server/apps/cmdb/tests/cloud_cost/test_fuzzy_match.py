# -*- coding: utf-8 -*-
"""CloudCostService 三个筛选维度(对象类型 / 使用部门 / 申请人)的模糊匹配测试。

约定(2026-07-14 改造):
- 三个维度(对应 bill 上的 object_type / user_department / applicant)统一走子串匹配
- 大小写不敏感(由 orm 层透传 case_sensitive=False 到 InstanceManage.instance_list,
  最终由 graph.format_str_like_params 翻译为 toLower() CONTAINS toLower())
- 现有 3 widget 口径一致性在模糊场景下也必须成立
- 老测试用完整字符串(例如 "database"、"alice"、"研发部")作为输入,模糊匹配结果不变,
  本文件只补「子串 + 大小写不敏感」覆盖
"""
from datetime import date
from decimal import Decimal

import pytest

from apps.cmdb.services.cloud_cost.service import CloudCostService


# ----- 1. 子串匹配 -----

def test_summary_substring_inst_type(stub_orm):
    """inst_type="data" 是 "database" 的子串,应命中 bill 1,2(都是 database)。"""
    result = CloudCostService.summary(stub_orm["user_info"], inst_type="data")
    assert result["total_cost"] == Decimal("600.00")
    assert result["instance_count"] == 2


def test_summary_substring_applying_user(stub_orm):
    """applying_user="ali" 是 "alice" 的子串,应命中 bill 1,2。"""
    result = CloudCostService.summary(stub_orm["user_info"], applying_user="ali")
    assert result["total_cost"] == Decimal("600.00")
    assert result["instance_count"] == 2


def test_summary_substring_department(stub_orm):
    """user_department="研发" 是 "研发部" 的子串,应命中 bill 1,2。"""
    result = CloudCostService.summary(stub_orm["user_info"], user_department="研发")
    assert result["total_cost"] == Decimal("600.00")
    assert result["instance_count"] == 2


def test_summary_substring_no_match(stub_orm):
    """输入子串在所有 bill 上都不存在 → 全部归零。"""
    result = CloudCostService.summary(stub_orm["user_info"], inst_type="zzz")
    assert result["total_cost"] == Decimal("0.00")
    assert result["instance_count"] == 0


# ----- 2. 大小写不敏感 -----

def test_summary_case_insensitive_inst_type(stub_orm):
    """'DATABASE' 应能命中 'database'(中文字段无大小写问题;英文需 case_sensitive=False)。"""
    result = CloudCostService.summary(stub_orm["user_info"], inst_type="DATABASE")
    assert result["total_cost"] == Decimal("600.00")
    assert result["instance_count"] == 2


def test_summary_case_insensitive_applying_user(stub_orm):
    """'ALICE' 应能命中 'alice'。"""
    result = CloudCostService.summary(stub_orm["user_info"], applying_user="ALICE")
    assert result["total_cost"] == Decimal("600.00")
    assert result["instance_count"] == 2


def test_summary_case_insensitive_substring(stub_orm):
    """'DaTaBaSe' 作为大小写不一致的子串也应命中 'database'。"""
    result = CloudCostService.summary(stub_orm["user_info"], inst_type="DaTaBaSe")
    assert result["total_cost"] == Decimal("600.00")


# ----- 3. 联合筛选:子串 + 子串(AND) -----

def test_summary_substring_combo_match(stub_orm):
    """inst_type 子串 + applying_user 子串都成立 → 命中交集。"""
    result = CloudCostService.summary(
        stub_orm["user_info"], inst_type="data", applying_user="lic"
    )
    assert result["total_cost"] == Decimal("600.00")
    assert result["instance_count"] == 2


def test_summary_substring_combo_no_intersection(stub_orm):
    """'data'(database 类) + 'bob'(运维 cache 类)无交集 → 归零。"""
    result = CloudCostService.summary(
        stub_orm["user_info"], inst_type="data", applying_user="bob"
    )
    assert result["total_cost"] == Decimal("0.00")
    assert result["instance_count"] == 0


# ----- 4. distribution 模糊分组 -----

def test_distribution_substring_inst_type(stub_orm):
    """inst_type='e' 同时命中 database / cache / compute(都含 'e'):
    database=d-a-t-a-b-a-s-e;cache=c-a-c-h-e;compute=c-o-m-p-u-t-e。
    因此 distribution 产出 3 组,合计 100%。
    """
    rows = CloudCostService.distribution(
        stub_orm["user_info"], inst_type="e", group_by="instance_type"
    )
    keys = {row["key"] for row in rows}
    assert keys == {"database", "cache", "compute"}
    total_pct = sum(row["pct"] for row in rows)
    assert abs(total_pct - 100.0) < 0.01


def test_distribution_substring_applying_user(stub_orm):
    """applying_user='a' 命中 alice 和 charlie(bob 不含 'a')。"""
    rows = CloudCostService.distribution(
        stub_orm["user_info"], applying_user="a", group_by="user"
    )
    keys = {row["key"] for row in rows}
    assert keys == {"alice", "charlie"}
    # alice 2 bill × 300 = 600;charlie 1 bill × 300 = 300;合计 900
    assert sum(row["total_cost"] for row in rows) == 900.0


# ----- 5. instance_list 模糊筛选 -----

def test_instance_list_substring_filter(stub_orm):
    """inst_type='data' → 只返 bill 1,2(都是 database)。"""
    result = CloudCostService.instance_list(
        stub_orm["user_info"], inst_type="data", page_size=100
    )
    assert result["total"] == 2
    assert {i["object_id"] for i in result["items"]} == {"res-1", "res-2"}


def test_instance_list_case_insensitive_filter(stub_orm):
    """'ALICE' + '研发部' 大小写不一致也应命中 bill 1,2。"""
    result = CloudCostService.instance_list(
        stub_orm["user_info"],
        applying_user="ALICE",
        user_department="研",
        page_size=100,
    )
    assert result["total"] == 2
    for item in result["items"]:
        assert item["user"] == "alice"
        assert item["department"] == "研发部"


# ----- 6. 模糊场景下 3 widget 一致性 -----

def test_three_widget_consistency_under_fuzzy_filter(stub_orm):
    """summary.total_cost == sum(distribution) == sum(instance_list) 在模糊场景下也成立。"""
    kw = {"inst_type": "data", "applying_user": "a"}
    s = CloudCostService.summary(stub_orm["user_info"], **kw)
    d = CloudCostService.distribution(stub_orm["user_info"], group_by="instance_type", **kw)
    il = CloudCostService.instance_list(stub_orm["user_info"], page_size=1000, **kw)

    d_total = sum((Decimal(str(row["total_cost"])) for row in d), Decimal("0"))
    i_total = sum((i["total_cost_incurred"] for i in il["items"]), Decimal("0"))
    assert s["total_cost"] == d_total == i_total


# ----- 7. 空值/None 透传:前端不传某维度时,不能因为模糊而改变"不过滤"语义 -----

def test_summary_none_filter_returns_all(stub_orm):
    """所有维度都传 None → 走全量,无空字符串泄漏。"""
    result = CloudCostService.summary(
        stub_orm["user_info"], inst_type=None, user_department=None, applying_user=None
    )
    assert result["total_cost"] == Decimal("1200.00")
    assert result["instance_count"] == 4


# ----- 8. 与 billing_period 联用:模糊筛选 + 时间窗 -----

def test_summary_substring_with_billing_period(stub_orm):
    """模糊子串 + 时间窗:子串"data"命中 bill 1,2,时间窗 2026-05 内 2 条 log(各 100) = 200。"""
    result = CloudCostService.summary(
        stub_orm["user_info"],
        inst_type="data",
        billing_period=(date(2026, 5, 1), date(2026, 5, 31)),
    )
    assert result["total_cost"] == Decimal("200.00")
    assert result["instance_count"] == 2
