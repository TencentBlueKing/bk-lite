# -*- coding: utf-8 -*-
"""cloud_cost.orm 单元测试。

策略:mock 图层(InstanceManage)+ 短路 _perm,不写真实 FalkorDB(图写不回滚,会污染 cmdb_graph)。
验证:参数拼装(真实字段名 object_type/applicant)、bill→log 关联反哺 _bill_id、权限短路。
"""
import pytest

from apps.cmdb.services.cloud_cost import orm


@pytest.fixture
def patch_perm(monkeypatch):
    """让 _perm 返回一个非 None 的假 permission_map,跳过真实 User/team 依赖。"""
    monkeypatch.setattr(orm, "_perm", lambda user_info, model_id: {"fake": True})


class FakeInstanceManage:
    """记录 instance_list 调用,并按 model_id 返回预置数据。"""

    def __init__(self, list_returns=None, assoc_return=None):
        # list_returns: {model_id: (list, count)}
        self.list_returns = list_returns or {}
        self.assoc_return = assoc_return or {}
        self.list_calls = []
        self.assoc_calls = []

    def instance_list(self, model_id, params, page, page_size, order, permission_map, creator="", case_sensitive=False):
        self.list_calls.append({"model_id": model_id, "params": params, "case_sensitive": case_sensitive})
        return self.list_returns.get(model_id, ([], 0))

    def instance_association_map(self, model_id, inst_ids, related_model=None):
        self.assoc_calls.append({"model_id": model_id, "inst_ids": inst_ids, "related_model": related_model})
        return self.assoc_return


def _install(monkeypatch, fake):
    # instance_list / instance_association_map 是 staticmethod,直接替换为 fake 的绑定方法
    monkeypatch.setattr(orm.InstanceManage, "instance_list", fake.instance_list)
    monkeypatch.setattr(orm.InstanceManage, "instance_association_map", fake.instance_association_map)


USER = {"team": 1, "user": "tester"}


# ---------- query_bills_by_filter ----------

def test_bills_no_filter_empty_params(monkeypatch, patch_perm):
    fake = FakeInstanceManage(list_returns={"resource_bill": ([{"_id": 1}], 1)})
    _install(monkeypatch, fake)
    bills, total = orm.query_bills_by_filter(USER)
    assert total == 1
    assert fake.list_calls[0]["model_id"] == "resource_bill"
    assert fake.list_calls[0]["params"] == []


def test_bills_inst_type_maps_to_object_type(monkeypatch, patch_perm):
    fake = FakeInstanceManage(list_returns={"resource_bill": ([], 0)})
    _install(monkeypatch, fake)
    orm.query_bills_by_filter(USER, inst_type="database")
    params = fake.list_calls[0]["params"]
    assert {"field": "object_type", "type": "str*", "value": "database"} in params


def test_bills_applying_user_maps_to_applicant(monkeypatch, patch_perm):
    fake = FakeInstanceManage(list_returns={"resource_bill": ([], 0)})
    _install(monkeypatch, fake)
    orm.query_bills_by_filter(USER, applying_user="alice")
    params = fake.list_calls[0]["params"]
    assert {"field": "applicant", "type": "str*", "value": "alice"} in params


def test_bills_user_department_kept(monkeypatch, patch_perm):
    fake = FakeInstanceManage(list_returns={"resource_bill": ([], 0)})
    _install(monkeypatch, fake)
    orm.query_bills_by_filter(USER, user_department="研发部")
    params = fake.list_calls[0]["params"]
    assert {"field": "user_department", "type": "str*", "value": "研发部"} in params


def test_bills_ignores_billing_period_with_warning(monkeypatch, patch_perm, caplog):
    from datetime import date
    fake = FakeInstanceManage(list_returns={"resource_bill": ([], 0)})
    _install(monkeypatch, fake)
    with caplog.at_level("WARNING"):
        orm.query_bills_by_filter(USER, billing_period=(date(2026, 6, 1), date(2026, 6, 30)))
    assert "billing_period" in caplog.text
    # billing_period 不应出现在 bill 查询 params 里
    assert all(p.get("field") != "billing_date" for p in fake.list_calls[0]["params"])


def test_bills_permission_none_short_circuits(monkeypatch):
    monkeypatch.setattr(orm, "_perm", lambda user_info, model_id: None)
    fake = FakeInstanceManage()
    _install(monkeypatch, fake)
    bills, total = orm.query_bills_by_filter(USER, inst_type="database")
    assert (bills, total) == ([], 0)
    assert fake.list_calls == []  # 无权限时不查库


# ---------- query_logs_by_filter ----------

def test_logs_always_resolve_via_bill_with_time_param(monkeypatch, patch_perm):
    """无 bill 维度也要经 bill 解析归属,并带 billing_date time 过滤 + 反哺 _bill_id。"""
    from datetime import date
    fake = FakeInstanceManage(
        list_returns={
            "resource_bill": ([{"_id": 1}], 1),
            "transaction_log": ([{"_id": 104}], 1),
        },
        assoc_return={1: [104]},
    )
    _install(monkeypatch, fake)
    logs, total = orm.query_logs_by_filter(USER, billing_period=(date(2026, 6, 1), date(2026, 6, 30)))
    assert total == 1
    log_call = [c for c in fake.list_calls if c["model_id"] == "transaction_log"][0]
    assert {"field": "billing_date", "type": "time", "start": "2026-06-01", "end": "2026-06-30"} in log_call["params"]
    assert logs[0]["_bill_id"] == 1  # 无筛选也反哺 _bill_id


def test_logs_bill_dim_path_backfills_bill_id(monkeypatch, patch_perm):
    """bill 维度:先筛 bill → 关联出 log → 查 log → 反哺 _bill_id。"""
    fake = FakeInstanceManage(
        list_returns={
            "resource_bill": ([{"_id": 275}, {"_id": 276}], 2),
            "transaction_log": ([{"_id": 287}, {"_id": 284}], 2),
        },
        assoc_return={275: [287, 288, 289], 276: [284, 285, 286]},
    )
    _install(monkeypatch, fake)
    logs, total = orm.query_logs_by_filter(USER, user_department="研发部")
    # 关联被调用,且用 bill_ids
    assert fake.assoc_calls[0]["inst_ids"] == [275, 276]
    assert fake.assoc_calls[0]["related_model"] == "transaction_log"
    # log 查询用 id[] 过滤
    log_call = [c for c in fake.list_calls if c["model_id"] == "transaction_log"][0]
    id_param = [p for p in log_call["params"] if p["type"] == "id[]"][0]
    assert set(id_param["value"]) == {284, 285, 286, 287, 288, 289}
    # _bill_id 反哺正确
    by_id = {lg["_id"]: lg["_bill_id"] for lg in logs}
    assert by_id[287] == 275
    assert by_id[284] == 276


def test_logs_bill_dim_no_bill_match_returns_empty(monkeypatch, patch_perm):
    fake = FakeInstanceManage(list_returns={"resource_bill": ([], 0)})
    _install(monkeypatch, fake)
    logs, total = orm.query_logs_by_filter(USER, user_department="不存在的部门")
    assert (logs, total) == ([], 0)
    # 没查到 bill 就不应发起关联/log 查询
    assert fake.assoc_calls == []


def test_logs_permission_none_short_circuits(monkeypatch):
    monkeypatch.setattr(orm, "_perm", lambda user_info, model_id: None)
    fake = FakeInstanceManage()
    _install(monkeypatch, fake)
    assert orm.query_logs_by_filter(USER, billing_period=None) == ([], 0)
    assert fake.list_calls == []


# ---------- query_bills_by_object_ids ----------

def test_bills_by_object_ids(monkeypatch, patch_perm):
    fake = FakeInstanceManage(list_returns={"resource_bill": ([{"_id": 1}, {"_id": 2}], 2)})
    _install(monkeypatch, fake)
    bills, total = orm.query_bills_by_object_ids(USER, [1, 2])
    assert total == 2
    id_param = [p for p in fake.list_calls[0]["params"] if p["type"] == "id[]"][0]
    assert id_param["value"] == [1, 2]


def test_bills_by_object_ids_empty():
    assert orm.query_bills_by_object_ids(USER, []) == ([], 0)


# ---------- 模糊筛选透传 ----------

def test_query_bills_forwards_case_insensitive(monkeypatch, patch_perm):
    """三个 bill 维度筛选(inst_type / user_department / applying_user)在拼装成
    str* 类型后,调用 InstanceManage.instance_list 时必须透传 case_sensitive=False,
    以保证子串匹配的大小写不敏感语义(参见 format_str_like_params)。
    """
    fake = FakeInstanceManage(list_returns={"resource_bill": ([], 0)})
    _install(monkeypatch, fake)
    orm.query_bills_by_filter(
        USER, inst_type="db", user_department="研", applying_user="al"
    )
    call = fake.list_calls[0]
    assert call["case_sensitive"] is False
    # 三个维度都按 str* 输出,且 case_sensitive 由 instance_list 透传,
    # 不在 params 自身里(透传点位于 instance_list 默认参数)
    types = {p["type"] for p in call["params"]}
    assert "str*" in types
    assert "str=" not in types


def test_query_logs_forwards_case_insensitive(monkeypatch, patch_perm):
    """log 查询(经 bill 解析)同样需要 case_sensitive=False。"""
    from datetime import date
    fake = FakeInstanceManage(
        list_returns={
            "resource_bill": ([{"_id": 1}], 1),
            "transaction_log": ([{"_id": 101}], 1),
        },
        assoc_return={1: [101]},
    )
    _install(monkeypatch, fake)
    orm.query_logs_by_filter(USER, inst_type="db", billing_period=(date(2026, 6, 1), date(2026, 6, 30)))
    # bill + log 两条调用都要传 case_sensitive=False
    assert all(c["case_sensitive"] is False for c in fake.list_calls)
