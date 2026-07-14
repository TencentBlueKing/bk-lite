# -*- coding: utf-8 -*-
"""「申请人 + 对象类型」联合筛选回归测试。

背景:
- 运维大屏的 3 个云资源费用 widget(source_api.json 中:
  云资源成本汇总 / 云资源费用分布 / 云资源账单明细)
  在 2026-07-14 把 filter 从 [部门, 计费日期] 扩到
  [部门, 申请人, 对象类型, 计费日期]。
- 本文件锁住「同时按 applicant + inst_type 筛选」时,三件套的口径和
  nats handler 的 kwargs 透传,避免后端某天把字段名改回去而前端无感。

测试夹具见 conftest.py:stub_orm 用内存数据替换 orm 两个查询函数,
4 bill (database×2/alice, cache×1/bob, compute×1/charlie) × 3 log / bill。
"""
from decimal import Decimal

from apps.cmdb.services.cloud_cost.service import CloudCostService


# ----- 1. summary -----

def test_summary_inst_type_plus_applying_user_hits_expected(stub_orm):
    """database + alice → 命中 bill 1,2(都是 database / alice),共 6 log × 100 = 600.00。"""
    result = CloudCostService.summary(
        stub_orm["user_info"],
        inst_type="database",
        applying_user="alice",
    )
    assert result["total_cost"] == Decimal("600.00")
    assert result["instance_count"] == 2  # res-1, res-2
    # 无 billing_period → 分母 = log 跨度天数(04-15 ~ 06-15 = 62 天)
    assert result["avg_daily_cost"] == (Decimal("600.00") / Decimal(62)).quantize(Decimal("0.01"))


def test_summary_mismatched_combo_returns_zero(stub_orm):
    """database + bob 永远无交集(bob 只有 cache),三个口径必须全部归零。"""
    result = CloudCostService.summary(
        stub_orm["user_info"],
        inst_type="database",
        applying_user="bob",
    )
    assert result["total_cost"] == Decimal("0")
    assert result["instance_count"] == 0
    assert result["avg_daily_cost"] == Decimal("0")
    assert result["mom_change_pct"] is None


def test_summary_with_billing_period_combo(stub_orm):
    """加 billing_period 后,3 log 里只 1 log 落在 2026-05 窗口。"""
    from datetime import date
    result = CloudCostService.summary(
        stub_orm["user_info"],
        inst_type="database",
        applying_user="alice",
        billing_period=(date(2026, 5, 1), date(2026, 5, 31)),
    )
    # 2026-05 落在 04/05/06 三月里的 05 一条 log,bill 1+2 各 1 条 → 共 2 条 × 100 = 200
    assert result["total_cost"] == Decimal("200.00")
    assert result["instance_count"] == 2  # DISTINCT object_id
    # 日历天数 = 31
    assert result["avg_daily_cost"] == (Decimal("200.00") / Decimal(31)).quantize(Decimal("0.01"))


# ----- 2. distribution -----

def test_distribution_combo_group_by_instance_type(stub_orm):
    """database+alice → 单组 "database", 600, 2 inst, 100%。"""
    rows = CloudCostService.distribution(
        stub_orm["user_info"],
        inst_type="database",
        applying_user="alice",
        group_by="instance_type",
    )
    assert rows == [
        {"key": "database", "total_cost": 600.0, "instance_count": 2, "pct": 100.0},
    ]


def test_distribution_combo_group_by_user(stub_orm):
    """database+alice → 按申请人分组,也是单组 "alice"。"""
    rows = CloudCostService.distribution(
        stub_orm["user_info"],
        inst_type="database",
        applying_user="alice",
        group_by="user",
    )
    assert rows == [
        {"key": "alice", "total_cost": 600.0, "instance_count": 2, "pct": 100.0},
    ]


def test_distribution_combo_mismatch_returns_empty(stub_orm):
    """database+bob 无交集,分布图无组。"""
    rows = CloudCostService.distribution(
        stub_orm["user_info"],
        inst_type="database",
        applying_user="bob",
        group_by="instance_type",
    )
    assert rows == []


# ----- 3. instance_list -----

def test_instance_list_combo_returns_matching_bills_only(stub_orm):
    """database+alice → bill 1, 2 入表;bill 3 (cache/bob) 4 (compute/charlie) 都不入。"""
    result = CloudCostService.instance_list(
        stub_orm["user_info"],
        inst_type="database",
        applying_user="alice",
        page_size=100,
    )
    assert result["total"] == 2
    object_ids = {item["object_id"] for item in result["items"]}
    assert object_ids == {"res-1", "res-2"}
    for item in result["items"]:
        assert item["object_type"] == "database"
        assert item["user"] == "alice"
        assert item["department"] == "研发部"
        assert item["total_cost_incurred"] == Decimal("300.00")  # 3 log × 100


def test_instance_list_combo_mismatch_returns_empty(stub_orm):
    result = CloudCostService.instance_list(
        stub_orm["user_info"],
        inst_type="database",
        applying_user="bob",
    )
    assert result["total"] == 0
    assert result["items"] == []


# ----- 4. 三件套口径一致性(组合筛选下也必须一致) -----

def test_consistency_under_combo_filter(stub_orm):
    """summary.total_cost == sum(distribution) == sum(instance_list.items)。
    组合筛选下也必须成立,这是 2026-07-14 改 filter 列表后最容易回归的口径。
    """
    kw = {"inst_type": "database", "applying_user": "alice"}
    s = CloudCostService.summary(stub_orm["user_info"], **kw)
    d = CloudCostService.distribution(stub_orm["user_info"], group_by="instance_type", **kw)
    il = CloudCostService.instance_list(stub_orm["user_info"], page_size=1000, **kw)

    d_total = sum((Decimal(str(row["total_cost"])) for row in d), Decimal("0"))
    i_total = sum((i["total_cost_incurred"] for i in il["items"]), Decimal("0"))
    assert s["total_cost"] == d_total == i_total == Decimal("600.00")


# ----- 5. nats handler kwargs 透传(锁定参数名) -----

class _RecordingService:
    """记录最近一次调用参数,代替真实 CloudCostService。"""

    def __init__(self):
        self.last = None

    def summary(self, user_info, **kw):
        self.last = {"user_info": user_info, **kw}
        return {"total_cost": 0, "instance_count": 0, "avg_daily_cost": 0, "mom_change_pct": None}

    def distribution(self, user_info, **kw):
        self.last = {"user_info": user_info, **kw}
        return []

    def instance_list(self, user_info, **kw):
        self.last = {"user_info": user_info, **kw}
        return {"total": 0, "page": 1, "page_size": 20, "items": []}


def test_nats_handler_forwards_inst_type_and_applying_user(monkeypatch):
    """3 个 nats handler 必须把前端传进来的 inst_type / applying_user
    原样转给 service;若哪天有人把字段名改回去,本测试会立刻失败。
    """
    from apps.cmdb.nats import nats
    from apps.cmdb.services.cloud_cost import service as service_mod

    rec = _RecordingService()
    monkeypatch.setattr(service_mod, "CloudCostService", rec)
    # service.py 内部 `from apps.cmdb.services.cloud_cost.service import CloudCostService`
    # 已锁定,直接替换 service_mod 里的 CloudCostService 即可。

    base = {"user_info": {"team": 1}}
    expected = {
        "summary": (nats.get_cloud_resource_cost_summary, "summary"),
        "distribution": (nats.get_cloud_resource_cost_distribution, "distribution"),
        "instance_list": (nats.get_cloud_resource_cost_bill_detail, "instance_list"),
    }

    for tag, (fn, method_name) in expected.items():
        rec.last = None
        fn(
            **base,
            department="研发部",
            applying_user="alice",
            inst_type="database",
            billing_period=None,
            group_by="instance_type" if tag == "distribution" else None,
            page=1 if tag == "instance_list" else None,
            page_size=20 if tag == "instance_list" else None,
        )
        assert rec.last is not None, f"{tag} handler did not call service"
        assert rec.last["inst_type"] == "database", f"{tag}: inst_type lost"
        assert rec.last["applying_user"] == "alice", f"{tag}: applying_user lost"
        assert rec.last["user_department"] == "研发部", f"{tag}: department lost"
