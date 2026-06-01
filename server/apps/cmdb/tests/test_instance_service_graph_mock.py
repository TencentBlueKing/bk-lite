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
