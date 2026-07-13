"""CMDB Neo4j 客户端覆盖测试（fake session，不连真实服务）。

对照 spec/prd/CMDB·搜索/资产：Neo4j 驱动的 CQL 构建、属性格式化、结果转换、校验逻辑。
"""

import pytest

from apps.cmdb.graph.neo4j import Neo4jClient
from apps.core.exceptions.base_app_exception import BaseAppException


# --------------------------------------------------------------------------
# fake neo4j objects
# --------------------------------------------------------------------------


class FakeNode:
    def __init__(self, node_id, labels, properties):
        self.id = node_id
        self.labels = labels
        self._properties = properties

    def __iter__(self):
        return iter(self._properties.items())

    def keys(self):
        return self._properties.keys()

    def __getitem__(self, k):
        return self._properties[k]


class FakeRel:
    def __init__(self, rel_id, rel_type, properties, start_node=None, end_node=None):
        self.id = rel_id
        self.type = rel_type
        self._properties = properties
        self.start_node = start_node
        self.end_node = end_node


class FakePath:
    def __init__(self, start_node, relationships, end_node):
        self.start_node = start_node
        self.relationships = relationships
        self.end_node = end_node


class FakeRunResult:
    """模拟 session.run() 返回：可迭代 + .single()。"""

    def __init__(self, records):
        self._records = records

    def __iter__(self):
        return iter(self._records)

    def single(self):
        return self._records[0] if self._records else None


class FakeSession:
    def __init__(self, result_records=None):
        self._records = result_records if result_records is not None else []
        self.last_query = None
        self.last_params = {}
        self.calls = []

    def run(self, query, *args, **kwargs):
        self.last_query = query
        self.last_params = kwargs
        self.calls.append((query, kwargs))
        return FakeRunResult(self._records)

    def close(self):
        pass


def _client(records=None):
    c = Neo4jClient.__new__(Neo4jClient)
    c.driver = None
    c.session = FakeSession(records)
    return c


# --------------------------------------------------------------------------
# 结果转换
# --------------------------------------------------------------------------


def test_entity_to_dict():
    c = _client()
    node = FakeNode(1, ["instance"], {"inst_name": "h1"})
    out = c.entity_to_dict((node,))
    assert out["_id"] == 1
    assert out["_label"] == "instance"
    assert out["inst_name"] == "h1"


def test_entity_to_list():
    c = _client()
    n1 = FakeNode(1, ["instance"], {"a": 1})
    n2 = FakeNode(2, ["instance"], {"a": 2})
    out = c.entity_to_list([(n1,), (n2,)])
    assert [o["_id"] for o in out] == [1, 2]


def test_edge_to_dict():
    c = _client()
    rel = FakeRel(5, "connects", {"model_asst_id": "conn"})
    out = c.edge_to_dict((rel,))
    assert out["_id"] == 5
    assert out["_label"] == "connects"
    assert out["model_asst_id"] == "conn"


def test_edge_to_list():
    c = _client()
    src = FakeNode(1, ["instance"], {"inst_name": "h"})
    dst = FakeNode(2, ["instance"], {"inst_name": "s"})
    rel = FakeRel(5, "connects", {"model_asst_id": "conn"})
    path = FakePath(src, [rel], dst)
    out = c.edge_to_list([(path,)], return_entity=True)
    assert out[0]["src"]["inst_name"] == "h"
    assert out[0]["edge"]["model_asst_id"] == "conn"
    assert out[0]["dst"]["inst_name"] == "s"
    # return_entity False → only edges
    out2 = c.edge_to_list([(path,)], return_entity=False)
    assert out2[0]["model_asst_id"] == "conn"


# --------------------------------------------------------------------------
# format helpers
# --------------------------------------------------------------------------


def test_format_properties():
    c = _client()
    out = c.format_properties({"name": "host", "count": 3})
    assert "name:'host'" in out and "count:3" in out


def test_format_properties_escapes():
    c = _client()
    assert "it\\'s" in c.format_properties({"name": "it's"})


def test_format_properties_set():
    c = _client()
    out = c.format_properties_set({"name": "host", "count": 3})
    assert "n.name='host'" in out


def test_format_properties_remove():
    c = _client()
    out = c.format_properties_remove(["old"])
    assert "old" in out


def test_format_search_params_str_eq():
    """format_search_params 返回 (str, dict) 元组，str 使用 $placeholder 不含原始值。"""
    c = _client()
    params_str, query_params = c.format_search_params([{"field": "name", "type": "str=", "value": "h"}])
    assert "n.name" in params_str
    # 参数化：原始值在 query_params 中，不在 CQL 字符串内
    assert "h" not in params_str
    assert "h" in query_params.values()


def test_format_search_params_supports_node_id_cursor():
    c = _client()
    params_str, query_params = c.format_search_params([{"field": "id", "type": "id>", "value": 12}])
    assert "ID(n) >" in params_str
    assert 12 in query_params.values()


def test_format_search_params_injection_value():
    """注入载荷在 query_params 中，不出现在 CQL 字符串里（核心防注入验证）。"""
    c = _client()
    injection = "foo'] RETURN n //"
    params_str, query_params = c.format_search_params([{"field": "name", "type": "str=", "value": injection}])
    # 注入字符串绝不能直接拼进 CQL
    assert injection not in params_str
    assert "RETURN" not in params_str
    # 注入值通过参数传递
    assert injection in query_params.values()


def test_format_search_params_injection_field():
    """非法 field 名（含注入字符）应被 CQLValidator 拒绝。"""
    from apps.core.exceptions.base_app_exception import BaseAppException
    c = _client()
    with pytest.raises((BaseAppException, Exception)):
        c.format_search_params([{"field": "name'] RETURN n //", "type": "str=", "value": "v"}])


def test_format_final_params():
    c = _client()
    combined_str, query_params = c.format_final_params([], permission_params="n.org=1")
    assert combined_str == "n.org=1"


def test_query_entity_can_page_without_count_query():
    c = _client([(FakeNode(1, ["instance"], {"name": "h1"}),)])

    rows, count = c.query_entity("instance", [], page={"skip": 0, "limit": 10}, include_count=False)

    assert len(rows) == 1
    assert count is None
    assert len(c.session.calls) == 1
    assert "SKIP 0 LIMIT 10" in c.session.calls[0][0]


# --------------------------------------------------------------------------
# check helpers
# --------------------------------------------------------------------------


def test_check_unique_attr_conflict():
    c = _client()
    with pytest.raises(BaseAppException):
        c.check_unique_attr({"name": "h"}, {"name": "名称"}, [{"name": "h"}])


def test_check_required_attr_missing():
    c = _client()
    with pytest.raises(BaseAppException):
        c.check_required_attr({"name": ""}, {"name": "名称"})


def test_get_editable_attr():
    c = _client()
    assert c.get_editable_attr({"a": 1, "b": 2}, {"a": "A"}) == {"a": 1}


# --------------------------------------------------------------------------
# query / create / delete（fake session）
# --------------------------------------------------------------------------


def test_query_entity():
    node = FakeNode(1, ["instance"], {"inst_name": "h1"})
    c = _client([(node,)])
    result, count = c.query_entity(label="instance", params=[])
    assert result[0]["inst_name"] == "h1"
    assert "MATCH (n:instance)" in c.session.last_query


def test_query_entity_by_id():
    node = FakeNode(7, ["instance"], {"inst_name": "h"})
    c = _client([(node,)])
    out = c.query_entity_by_id(7)
    assert out["_id"] == 7


def test_create_entity():
    created = FakeNode(9, ["instance"], {"inst_name": "new"})
    c = _client([(created,)])
    out = c.create_entity(
        label="instance",
        properties={"inst_name": "new"},
        check_attr_map={"is_only": {}, "is_required": {}},
        exist_items=[],
        operator="admin",
    )
    assert out["_id"] == 9
    assert "CREATE" in c.session.last_query.upper()


def test_create_entity_required_missing():
    c = _client()
    with pytest.raises(BaseAppException):
        c.create_entity(
            label="instance",
            properties={"inst_name": ""},
            check_attr_map={"is_only": {}, "is_required": {"inst_name": "名称"}},
            exist_items=[],
        )


def test_batch_delete_entity():
    c = _client()
    c.batch_delete_entity("instance", [1, 2])
    assert "DETACH DELETE" in c.session.last_query.upper()


def test_detach_delete_entity():
    c = _client()
    c.detach_delete_entity("instance", 5)
    assert "DETACH DELETE" in c.session.last_query.upper()


def test_delete_edge():
    c = _client()
    c.delete_edge(3)
    assert "DELETE" in c.session.last_query.upper()


def test_query_edge():
    src = FakeNode(1, ["instance"], {"inst_name": "h", "model_id": "host"})
    dst = FakeNode(2, ["instance"], {"inst_name": "s", "model_id": "sw"})
    rel = FakeRel(5, "connects", {"model_asst_id": "conn"})
    path = FakePath(src, [rel], dst)
    c = _client([(path,)])
    out = c.query_edge(label="", params=[], return_entity=True)
    assert out[0]["edge"]["model_asst_id"] == "conn"


# --------------------------------------------------------------------------
# find_entity_by_id / create_node
# --------------------------------------------------------------------------


def test_find_entity_by_id():
    c = _client()
    entities = [{"_id": 1}, {"_id": 2}]
    assert c.find_entity_by_id(2, entities)["_id"] == 2
    assert c.find_entity_by_id(99, entities) is None


def test_create_node():
    c = _client()
    entity = {"_id": 1, "model_id": "host", "inst_name": "h1"}
    entities = [entity, {"_id": 2, "model_id": "sw", "inst_name": "s1"}]
    edges = [{"src_inst_id": 1, "dst_inst_id": 2, "model_asst_id": "conn", "asst_id": "a1"}]
    node = c.create_node(entity, edges, entities, entity_is_src=True)
    assert node["children"][0]["_id"] == 2
