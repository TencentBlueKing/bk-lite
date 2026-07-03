"""CMDB InstanceManage 服务层覆盖测试（mock GraphClient）。

对照 spec/prd/CMDB·资产：实例列表查询、关联实例查询、批量删除、按ID查询。
"""

import pytest

from apps.cmdb.services.instance import InstanceManage
from apps.core.exceptions.base_app_exception import BaseAppException


# --------------------------------------------------------------------------
# instance_list
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_instance_list(fake_graph):
    fake = fake_graph(
        "apps.cmdb.services.instance",
        query_entity=([{"_id": 1, "inst_name": "h1", "model_id": "host"}], 1),
    )
    insts, count = InstanceManage.instance_list(
        model_id="host", params=[], page=1, page_size=10, order="-inst_name", permission_map={},
    )
    assert count == 1
    assert insts[0]["inst_name"] == "h1"
    assert any(c[0] == "query_entity" for c in fake.calls)


# --------------------------------------------------------------------------
# query_entity_by_id / by_ids
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_query_entity_by_id(fake_graph):
    fake_graph("apps.cmdb.services.instance", query_entity_by_id={"_id": 7, "inst_name": "h"})
    out = InstanceManage.query_entity_by_id(7)
    assert out["_id"] == 7


@pytest.mark.django_db
def test_query_entity_by_ids(fake_graph):
    fake_graph("apps.cmdb.services.instance", query_entity_by_ids=[{"_id": 1}, {"_id": 2}])
    out = InstanceManage.query_entity_by_ids([1, 2])
    assert len(out) == 2


# --------------------------------------------------------------------------
# instance_association_instance_list
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_instance_association_instance_list(fake_graph):
    src_edges = [{
        "edge": {"_id": 100, "src_model_id": "host", "dst_model_id": "switch",
                 "model_asst_id": "host_conn_switch", "asst_id": "conn"},
        "src": {"_id": 1, "inst_name": "h1"},
        "dst": {"_id": 2, "inst_name": "s1"},
    }]

    def fake_query_edge(label, query, return_entity=False):
        # src 查询返回边，dst 查询返回空
        if any(q["field"] == "src_inst_id" for q in query):
            return src_edges
        return []

    fake_graph("apps.cmdb.services.instance", query_edge=fake_query_edge)
    result = InstanceManage.instance_association_instance_list("host", 1)
    assert result[0]["model_asst_id"] == "host_conn_switch"
    assert result[0]["inst_list"][0]["_id"] == 2


@pytest.mark.django_db
def test_instance_association(fake_graph):
    fake_graph("apps.cmdb.services.instance", query_edge=[{"_id": 1, "model_asst_id": "a"}])
    out = InstanceManage.instance_association("host", 1)
    # src + dst 各一条
    assert len(out) == 2


@pytest.mark.django_db
def test_instance_association_map(fake_graph):
    def fake_query_edge(label, query, return_entity=False, **kw):
        if any(q["field"] == "src_inst_id" for q in query):
            return [{"src_inst_id": 1, "dst_inst_id": 5}]
        return [{"dst_inst_id": 1, "src_inst_id": 9}]

    fake_graph("apps.cmdb.services.instance", query_edge=fake_query_edge)
    result = InstanceManage.instance_association_map("host", [1])
    assert set(result[1]) == {5, 9}


@pytest.mark.django_db
def test_instance_association_map_empty_ids(fake_graph):
    fake_graph("apps.cmdb.services.instance")
    assert InstanceManage.instance_association_map("host", []) == {}


# --------------------------------------------------------------------------
# instance_batch_delete
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_instance_batch_delete_not_found(fake_graph):
    fake_graph("apps.cmdb.services.instance", query_entity_by_ids=[])
    with pytest.raises(BaseAppException):
        InstanceManage.instance_batch_delete([], [], [1], "admin")


@pytest.mark.django_db
def test_instance_batch_delete_change_record_written_before_graph_delete(monkeypatch):
    """#3665: 变更记录必须先于图删除写入 PG，若 PG 写入失败则图删除不执行。

    验证手段：记录全局调用顺序，确认 batch_create_change_record 在 batch_delete_entity 之前。
    若 revert 修复（改回先图后 PG），batch_delete_entity 会排在 batch_create_change_record 之前，测试失败。
    """
    call_order = []

    inst_list = [{"_id": 1, "model_id": "host", "inst_name": "h1"}]

    monkeypatch.setattr(
        "apps.cmdb.services.instance.GraphClient",
        lambda *a, **k: _SpyGraphClient(call_order),
    )
    monkeypatch.setattr(
        "apps.cmdb.services.instance.InstanceManage.query_entity_by_ids",
        lambda *a, **kw: inst_list,
    )
    monkeypatch.setattr(
        "apps.cmdb.services.instance.ModelManage.search_model_info",
        lambda model_id: {"model_name": "主机"},
    )
    monkeypatch.setattr(
        "apps.cmdb.services.instance.InstanceManage.check_instances_permission",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "apps.cmdb.services.instance.get_instance_enterprise_extension",
        lambda: type("Ext", (), {"on_instances_delete": lambda self, x: None})(),
    )

    def spy_batch_create_change_record(*args, **kwargs):
        call_order.append("batch_create_change_record")

    monkeypatch.setattr(
        "apps.cmdb.services.instance.batch_create_change_record",
        spy_batch_create_change_record,
    )
    monkeypatch.setattr(
        "apps.cmdb.services.auto_relation_reconcile.schedule_incoming_rule_full_sync_by_model_ids",
        lambda x: None,
        raising=False,
    )

    InstanceManage.instance_batch_delete([], [], [1], "admin")

    # 核心断言：PG 写入必须先于图删除
    assert call_order.index("batch_create_change_record") < call_order.index("batch_delete_entity"), (
        "batch_create_change_record 应在 batch_delete_entity 之前调用，"
        "否则 PG 失败时图删除已提交、审计日志丢失（#3665）"
    )


class _SpyGraphClient:
    """记录 batch_delete_entity 调用顺序的 spy graph client。"""

    def __init__(self, call_order: list):
        self._call_order = call_order

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def batch_delete_entity(self, *args, **kwargs):
        self._call_order.append("batch_delete_entity")


@pytest.mark.django_db
def test_instance_batch_delete_pg_failure_prevents_graph_delete(fake_graph, monkeypatch):
    """#3665: 若 PG 变更记录写入失败，图删除不应执行（先写 PG 保障一致性）。"""
    inst_list = [{"_id": 1, "model_id": "host", "inst_name": "h1"}]

    graph_delete_called = []

    monkeypatch.setattr(
        "apps.cmdb.services.instance.GraphClient",
        lambda *a, **k: _SpyGraphClient(graph_delete_called),
    )
    monkeypatch.setattr(
        "apps.cmdb.services.instance.InstanceManage.query_entity_by_ids",
        lambda *a, **kw: inst_list,
    )
    monkeypatch.setattr(
        "apps.cmdb.services.instance.ModelManage.search_model_info",
        lambda model_id: {"model_name": "主机"},
    )
    monkeypatch.setattr(
        "apps.cmdb.services.instance.InstanceManage.check_instances_permission",
        lambda *a, **kw: None,
    )

    def failing_batch_create_change_record(*args, **kwargs):
        raise Exception("PG connection error")

    monkeypatch.setattr(
        "apps.cmdb.services.instance.batch_create_change_record",
        failing_batch_create_change_record,
    )

    with pytest.raises(Exception, match="PG connection error"):
        InstanceManage.instance_batch_delete([], [], [1], "admin")

    # 核心断言：PG 失败后图删除不应被调用
    assert "batch_delete_entity" not in graph_delete_called, (
        "PG 写入失败时图删除不应执行，否则实例消失但无审计日志（#3665）"
    )


@pytest.mark.django_db
def test_instance_association_create_pg_failure_does_not_propagate(fake_graph, monkeypatch):
    """#3665: instance_association_create 中 PG 变更记录写入失败不应向上传播。

    图边已创建后，PG 写入失败应仅记录日志，不影响关联创建结果（避免调用方误以为关联创建失败而重试）。
    """
    edge = {"_id": 99, "src_inst_id": 1, "dst_inst_id": 2, "model_asst_id": "host_run_proc"}
    asso_info = {
        "_id": 99,
        "src": {"_id": 1, "model_id": "host", "inst_name": "h1"},
        "dst": {"_id": 2, "model_id": "proc", "inst_name": "p1"},
    }

    fake_graph(
        "apps.cmdb.services.instance",
        create_edge=edge,
    )
    monkeypatch.setattr(
        "apps.cmdb.services.instance.InstanceManage.check_asso_mapping",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "apps.cmdb.services.instance.InstanceManage.instance_association_by_asso_id",
        lambda *a, **kw: asso_info,
    )

    def failing_create_change_record_by_asso(*args, **kwargs):
        raise Exception("PG write failure")

    monkeypatch.setattr(
        "apps.cmdb.services.instance.create_change_record_by_asso",
        failing_create_change_record_by_asso,
    )

    # 核心断言：即使 PG 失败，函数应正常返回 edge（不传播异常）
    result = InstanceManage.instance_association_create(
        {"src_inst_id": 1, "dst_inst_id": 2, "model_asst_id": "host_run_proc"}, "admin"
    )
    assert result == edge, "PG 变更记录失败不应影响关联创建返回值（#3665）"
