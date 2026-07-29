"""CMDB FalkorDB 客户端覆盖测试（fake 底层 graph，不连真实服务）。

对照 specs/capabilities/legacy-prd-cmdb-搜索.md：CQL 构建、属性转义/序列化、查询结果格式化、校验逻辑。
"""

import json
import threading

import pytest

from apps.cmdb.graph.falkordb import FalkorDBClient, FalkorDBConnectionPool
from apps.core.exceptions.base_app_exception import BaseAppException


# --------------------------------------------------------------------------
# fake graph result
# --------------------------------------------------------------------------


class FakeNode:
    def __init__(self, node_id, labels, properties):
        self.id = node_id
        self.labels = labels
        self.properties = properties


class FakeResultSet:
    def __init__(self, header, rows):
        self.header = header  # list of (type, name) tuples
        self.result_set = rows


class FakeGraph:
    """记录最后一次查询，并返回预置结果集。"""

    def __init__(self, result=None):
        self._result = result if result is not None else FakeResultSet([], [])
        self.last_query = None
        self.last_params = None
        self.calls = []

    def query(self, cql, params=None):
        self.last_query = cql
        self.last_params = params
        self.calls.append((cql, params))
        if callable(self._result):
            return self._result(cql, params)
        return self._result


def _client(result=None):
    c = FalkorDBClient()
    c._client = object()
    c._graph = FakeGraph(result)
    return c


def _entity_result(nodes):
    rows = [[node] for node in nodes]
    return FakeResultSet([("node", "n")], rows)


# --------------------------------------------------------------------------
# 纯静态 helpers
# --------------------------------------------------------------------------


def test_escape_cql_string():
    assert FalkorDBClient.escape_cql_string("a'b") == "a\\'b"
    assert FalkorDBClient.escape_cql_string("c\\d") == "c\\\\d"
    assert FalkorDBClient.escape_cql_string(123) == 123


def test_format_properties():
    out = FalkorDBClient.format_properties({"name": "host", "count": 3})
    assert "name:'host'" in out
    assert "count:3" in out


def test_format_properties_escapes():
    out = FalkorDBClient.format_properties({"name": "it's"})
    assert "it\\'s" in out


def test_build_exclude_fields_list():
    assert FalkorDBClient._build_exclude_fields_list([]) == "[]"
    out = FalkorDBClient._build_exclude_fields_list(["name", "1bad", "org"])
    # 1bad 不合法被跳过
    assert "'name'" in out and "'org'" in out
    assert "1bad" not in out


def test_format_properties_params():
    out = FalkorDBClient().format_properties_params({"a": 1})
    assert out == {"props": {"a": 1}}
    assert FalkorDBClient().format_properties_params({}) == {}


# --------------------------------------------------------------------------
# check helpers
# --------------------------------------------------------------------------


def test_check_unique_attr_conflict():
    check_attr_map = {"name": "名称"}
    exist = [{"name": "host1"}]
    with pytest.raises(BaseAppException):
        FalkorDBClient.check_unique_attr({"name": "host1"}, check_attr_map, exist)


def test_check_unique_attr_ok():
    FalkorDBClient.check_unique_attr({"name": "host2"}, {"name": "名称"}, [{"name": "host1"}])


def test_check_required_attr_missing():
    c = _client()
    with pytest.raises(BaseAppException):
        c.check_required_attr({"name": ""}, {"name": "名称"})


def test_check_required_attr_ok():
    c = _client()
    c.check_required_attr({"name": "host"}, {"name": "名称"})


def test_get_editable_attr():
    c = _client()
    out = c.get_editable_attr({"a": 1, "b": 2, "c": 3}, {"a": "A", "c": "C"})
    assert out == {"a": 1, "c": 3}


def test_serialize_table_fields():
    c = _client()
    attrs = [{"attr_id": "spec", "attr_type": "table"}]
    out = c._serialize_table_fields("instance", {"spec": [{"x": 1}]}, attrs)
    assert isinstance(out["spec"], str)
    assert json.loads(out["spec"]) == [{"x": 1}]


def test_serialize_table_fields_non_instance():
    c = _client()
    props = {"spec": [{"x": 1}]}
    assert c._serialize_table_fields("model", props, [{"attr_id": "spec", "attr_type": "table"}]) == props


# --------------------------------------------------------------------------
# format_search_params / format_final_params
# --------------------------------------------------------------------------


def test_format_search_params_empty():
    c = _client()
    cond, params = c.format_search_params([])
    assert cond == ""


def test_format_search_params_str_eq():
    c = _client()
    cond, params = c.format_search_params([{"field": "name", "type": "str=", "value": "host"}])
    assert "n.name" in cond
    assert "host" in params.values()


def test_format_search_params_supports_node_id_cursor():
    c = _client()
    cond, params = c.format_search_params([{"field": "id", "type": "id>", "value": 12}])
    assert "ID(n) >" in cond
    assert 12 in params.values()


def test_format_final_params_only_permission():
    c = _client()
    assert c.format_final_params([], permission_params="n.org = 1") == "n.org = 1"


def test_format_final_params_combined():
    c = _client()
    out = c.format_final_params(
        [{"field": "name", "type": "str=", "value": "h"}],
        permission_params="n.org = 1",
    )
    assert "AND n.org = 1" in out


# --------------------------------------------------------------------------
# query_entity / by_id / by_ids（fake graph）
# --------------------------------------------------------------------------


def test_query_entity_returns_formatted_nodes():
    nodes = [FakeNode(1, ["instance"], {"inst_name": "host1", "model_id": "host"})]
    c = _client(_entity_result(nodes))
    result, count = c.query_entity(label="instance", params=[])
    assert result[0]["inst_name"] == "host1"
    assert result[0]["_id"] == 1
    assert "MATCH (n:instance)" in c._graph.last_query


def test_query_entity_with_search_params():
    nodes = [FakeNode(1, ["instance"], {"inst_name": "host1"})]
    c = _client(_entity_result(nodes))
    c.query_entity(label="instance", params=[{"field": "inst_name", "type": "str=", "value": "host1"}])
    assert "WHERE" in c._graph.last_query


def test_query_entity_can_page_without_count_query():
    nodes = [FakeNode(1, ["instance"], {"inst_name": "host1"})]
    c = _client(_entity_result(nodes))

    rows, count = c.query_entity(
        label="instance",
        params=[],
        page={"skip": 0, "limit": 10},
        include_count=False,
    )

    assert len(rows) == 1
    assert count is None
    assert len(c._graph.calls) == 1
    assert "SKIP 0 LIMIT 10" in c._graph.calls[0][0]


def test_query_entity_invalid_label_raises():
    c = _client()
    with pytest.raises(BaseAppException):
        c.query_entity(label="bad label!", params=[])


def test_query_entity_by_id():
    nodes = [FakeNode(5, ["instance"], {"inst_name": "h"})]
    c = _client(_entity_result(nodes))
    out = c.query_entity_by_id(5)
    assert out["_id"] == 5


def test_query_entity_by_id_empty():
    c = _client(FakeResultSet([("node", "n")], []))
    assert c.query_entity_by_id(99) == {}


def test_query_entity_by_ids():
    nodes = [FakeNode(1, ["instance"], {"a": 1}), FakeNode(2, ["instance"], {"a": 2})]
    c = _client(_entity_result(nodes))
    out = c.query_entity_by_ids([1, 2])
    assert len(out) == 2


def test_query_entity_by_ids_invalid():
    c = _client()
    with pytest.raises(BaseAppException):
        c.query_entity_by_ids([])


# --------------------------------------------------------------------------
# set / remove properties build CQL
# --------------------------------------------------------------------------


def test_format_properties_set():
    c = _client()
    out = c.format_properties_set({"name": "host", "count": 3})
    assert "n.name" in out


def test_format_properties_remove():
    c = _client()
    out = c.format_properties_remove(["old_attr"])
    assert "old_attr" in out


def test_batch_delete_entity_builds_query():
    c = _client(FakeResultSet([], []))
    c.batch_delete_entity("instance", [1, 2])
    assert "DELETE" in c._graph.last_query.upper()


def test_entity_count_empty_params():
    # entity_count 在无结果时返回空
    c = _client(FakeResultSet([("count", "c")], []))
    result = c.entity_count("instance", group_by_attr="model_id")
    assert isinstance(result, (list, dict))


# --------------------------------------------------------------------------
# create_entity / set_entity_properties / batch ops（fake graph）
# --------------------------------------------------------------------------


def test_create_entity_success():
    created = FakeNode(7, ["instance"], {"inst_name": "newhost"})
    c = _client(_entity_result([created]))
    out = c.create_entity(
        label="instance",
        properties={"inst_name": "newhost"},
        check_attr_map={"is_only": {}, "is_required": {}},
        exist_items=[],
        operator="admin",
    )
    assert out["_id"] == 7
    assert "CREATE (n:instance)" in c._graph.last_query


def test_create_entity_required_missing():
    c = _client()
    with pytest.raises(BaseAppException):
        c.create_entity(
            label="instance",
            properties={"inst_name": ""},
            check_attr_map={"is_only": {}, "is_required": {"inst_name": "名称"}},
            exist_items=[],
        )


def test_create_entity_unique_conflict():
    c = _client()
    with pytest.raises(BaseAppException):
        c.create_entity(
            label="instance",
            properties={"inst_name": "dup"},
            check_attr_map={"is_only": {"inst_name": "名称"}, "is_required": {}},
            exist_items=[{"inst_name": "dup"}],
        )


def test_set_entity_properties_instance():
    updated = FakeNode(3, ["instance"], {"inst_name": "h", "desc": "new"})
    c = _client(_entity_result([updated]))
    out = c.set_entity_properties(
        label="instance",
        entity_ids=[3],
        properties={"desc": "new"},
        check_attr_map={"editable": {"desc": "描述"}},
        exist_items=[],
        check=True,
    )
    assert out[0]["_id"] == 3


def test_set_entity_properties_model_fills_defaults():
    attrs = [{"attr_id": "name", "attr_type": "str", "option": {}}]
    updated = FakeNode(1, ["model"], {"model_id": "host"})
    c = _client(_entity_result([updated]))
    c.set_entity_properties(
        label="model",
        entity_ids=[1],
        properties={"attrs": json.dumps(attrs)},
        check_attr_map={},
        exist_items=[],
        check=False,
    )
    assert "SET" in c._graph.last_query.upper()


def test_set_entity_properties_model_tolerates_legacy_option_type():
    attrs = [{"attr_id": "ip_status", "attr_type": "str", "option": [{"id": "online", "name": "在线"}]}]
    updated = FakeNode(1, ["model"], {"model_id": "ip"})
    c = _client(_entity_result([updated]))
    c.set_entity_properties(
        label="model",
        entity_ids=[1],
        properties={"attrs": json.dumps(attrs, ensure_ascii=False)},
        check_attr_map={},
        exist_items=[],
        check=False,
    )
    saved_attrs = json.loads(c._graph.last_params["val0"])
    assert saved_attrs[0]["option"]["validation_type"] == "unrestricted"


def test_batch_update_node_properties_empty_props_raises():
    c = _client()
    with pytest.raises(BaseAppException):
        c.batch_update_node_properties("instance", [1], {})


def test_batch_create_entity_mixed_results():
    created = FakeNode(1, ["instance"], {"inst_name": "ok"})
    c = _client(_entity_result([created]))
    results = c.batch_create_entity(
        label="instance",
        properties_list=[{"inst_name": "ok"}, {"inst_name": ""}],
        check_attr_map={"is_only": {}, "is_required": {"inst_name": "名称"}},
        exist_items=[],
    )
    assert results[0]["success"] is True
    assert results[1]["success"] is False


# --------------------------------------------------------------------------
# delete / remove / detach
# --------------------------------------------------------------------------


def test_detach_delete_entity():
    c = _client(FakeResultSet([], []))
    c.detach_delete_entity("instance", 5)
    assert "DETACH DELETE" in c._graph.last_query.upper()


def test_delete_edge():
    c = _client(FakeResultSet([], []))
    c.delete_edge(9)
    assert "DELETE" in c._graph.last_query.upper()


def test_remove_entitys_properties():
    c = _client(_entity_result([]))
    c.remove_entitys_properties("instance", [{"field": "inst_name", "type": "str=", "value": "h"}], ["old_attr"])
    assert "REMOVE" in c._graph.last_query.upper()


# --------------------------------------------------------------------------
# query_edge（fake edge path）
# --------------------------------------------------------------------------


class FakeEdge:
    def __init__(self, edge_id, properties):
        self.id = edge_id
        self.properties = properties


class FakePath:
    def __init__(self, edges, nodes):
        self._edges = edges
        self._nodes = nodes


def test_query_edge_returns_edges():
    edge = FakeEdge(1, {"src_model_id": "host", "dst_model_id": "switch", "model_asst_id": "conn"})
    src = FakeNode(10, ["instance"], {"model_id": "host", "inst_name": "h1"})
    dst = FakeNode(20, ["instance"], {"model_id": "switch", "inst_name": "s1"})
    path = FakePath([edge], [src, dst])
    result = FakeResultSet([("path", "p")], [[path]])
    c = _client(result)
    edges = c.query_edge(label="", params=[], return_entity=True)
    assert edges[0]["edge"]["model_asst_id"] == "conn"
    assert edges[0]["src"]["inst_name"] == "h1"


# --------------------------------------------------------------------------
# entity_objs / find_entity_by_id / create_node
# --------------------------------------------------------------------------


def test_entity_objs():
    c = _client(_entity_result([FakeNode(1, ["instance"], {})]))
    c.entity_objs("instance", [{"field": "inst_name", "type": "str=", "value": "h"}])
    assert "MATCH (n:instance)" in c._graph.last_query


def test_find_entity_by_id():
    c = _client()
    entities = [{"_id": 1, "name": "a"}, {"_id": 2, "name": "b"}]
    assert c.find_entity_by_id(2, entities)["name"] == "b"
    assert c.find_entity_by_id(99, entities) is None


def test_create_node_builds_tree():
    c = _client()
    entity = {"_id": 1, "model_id": "host", "inst_name": "h1"}
    entities = [entity, {"_id": 2, "model_id": "sw", "inst_name": "s1"}]
    edges = [{"src_inst_id": 1, "dst_inst_id": 2, "model_asst_id": "conn", "asst_id": "a1"}]
    node = c.create_node(entity, edges, entities, entity_is_src=True)
    assert node["_id"] == 1
    assert node["children"][0]["_id"] == 2


def test_create_node_lite_depth_limit():
    c = _client()
    entity = {"_id": 1, "model_id": "host", "inst_name": "h1"}
    entities = [entity, {"_id": 2, "model_id": "sw", "inst_name": "s1"}]
    edges = [{"src_inst_id": 1, "dst_inst_id": 2, "model_asst_id": "conn", "asst_id": "a1"}]
    node = c.create_node_lite(entity, edges, entities, entity_is_src=True, level=1, max_depth=1)
    # 达到深度上限 → has_more
    assert node.get("has_more") is True


# --------------------------------------------------------------------------
# topo (fake path with relation edges)
# --------------------------------------------------------------------------


class FakeRelEdge:
    def __init__(self, edge_id, relation, properties):
        self.id = edge_id
        self.relation = relation
        self.properties = properties


class FakeTopoElement:
    def __init__(self, nodes, edges):
        self._nodes = nodes
        self._edges = edges


def test_format_topo():
    c = _client()
    n1 = FakeNode(1, ["instance"], {"model_id": "host", "inst_name": "h1"})
    n2 = FakeNode(2, ["instance"], {"model_id": "sw", "inst_name": "s1"})
    e = FakeRelEdge(100, "connects", {"src_inst_id": 1, "dst_inst_id": 2, "model_asst_id": "conn", "asst_id": "a1"})
    element = FakeTopoElement([n1, n2], [e])
    objs = FakeResultSet([("path", "p")], [[element]])
    result = c.format_topo(1, objs, entity_is_src=True)
    assert result["_id"] == 1
    assert result["children"][0]["_id"] == 2


def test_format_topo_start_not_found():
    c = _client()
    objs = FakeResultSet([("path", "p")], [])
    assert c.format_topo(999, objs, entity_is_src=True) == {}


def test_query_topo():
    c = _client()
    n1 = FakeNode(1, ["instance"], {"model_id": "host", "inst_name": "h1"})
    n2 = FakeNode(2, ["instance"], {"model_id": "sw", "inst_name": "s1"})
    e = FakeRelEdge(100, "connects", {"src_inst_id": 1, "dst_inst_id": 2, "model_asst_id": "conn", "asst_id": "a1"})
    element = FakeTopoElement([n1, n2], [e])
    c._graph = FakeGraph(FakeResultSet([("path", "p")], [[element]]))
    out = c.query_topo("instance", 1)
    assert "src_result" in out and "dst_result" in out


# --------------------------------------------------------------------------
# query_entity 分页 + 权限 dict
# --------------------------------------------------------------------------


def test_query_entity_with_pagination_and_permission():
    nodes = [FakeNode(1, ["instance"], {"inst_name": "h1"})]

    def result(cql, params):
        if "COUNT(n)" in cql:
            return FakeResultSet([("count", "count")], [[5]])
        return _entity_result(nodes)

    c = _client(result)
    res, count = c.query_entity(
        label="instance",
        params=[],
        format_permission_dict={4: [{"field": "inst_name", "type": "str[]", "value": ["h1"]}]},
        page={"skip": 0, "limit": 10},
        order="inst_name",
    )
    assert count == 5
    assert res[0]["inst_name"] == "h1"
    assert "SKIP" in c._graph.last_query and "LIMIT" in c._graph.last_query


def test_query_entity_by_inst_names():
    nodes = [FakeNode(1, ["instance"], {"inst_name": "h1"})]
    c = _client(_entity_result(nodes))
    out = c.query_entity_by_inst_names(["h1"], model_id="host")
    assert out[0]["inst_name"] == "h1"
    assert "n.inst_name IN" in c._graph.last_query


def test_query_entity_by_inst_names_empty():
    c = _client(FakeResultSet([("node", "n")], []))
    assert c.query_entity_by_inst_names(["x"]) == []


# --------------------------------------------------------------------------
# batch_create_entity / batch_create_edge / batch_update_entity_properties
# --------------------------------------------------------------------------


def test_batch_create_edge_mixed():
    created_edge = FakeNode(1, ["connects"], {})  # edge_to_dict reads .properties via FormatDBResult

    def result(cql, params):
        if "COUNT(e)" in cql:
            return FakeResultSet([("count", "count")], [[0]])
        # create edge returns edge node
        return FakeResultSet([("edge", "e")], [[FakeRelEdge(1, "connects", {"model_asst_id": "c"})]])

    # edge_to_dict uses entity_to_dict which reads .properties; FakeRelEdge has .properties
    c = _client(result)
    edges = [{"src_id": 1, "dst_id": 2, "model_asst_id": "c"}]
    results = c.batch_create_edge("connects", "host", "switch", edges, "model_asst_id")
    assert results[0]["success"] is True


def test_batch_update_entity_properties():
    updated = FakeNode(1, ["instance"], {"inst_name": "h", "desc": "x"})
    c = _client(_entity_result([updated]))
    out = c.batch_update_entity_properties(
        label="instance", entity_ids=[1], properties={"desc": "x"}, check_attr_map={}, check=False,
    )
    assert out["success"] is True
    assert out["data"][0]["_id"] == 1


# --------------------------------------------------------------------------
# set_edge_properties
# --------------------------------------------------------------------------


def test_set_edge_properties():
    edge = FakeRelEdge(5, "connects", {"model_asst_id": "c"})
    c = _client(FakeResultSet([("edge", "e")], [[edge]]))
    out = c.set_edge_properties(5, {"model_asst_id": "c2"})
    assert out["_id"] == 5


def test_set_edge_properties_empty():
    c = _client()
    with pytest.raises(BaseAppException):
        c.set_edge_properties(5, {})


# --------------------------------------------------------------------------
# entity_count grouping
# --------------------------------------------------------------------------


def test_entity_count_grouped():
    # to_result_of_count expects rows of [key, count]
    result = FakeResultSet([("model_id", "model_id"), ("count", "count")], [["host", 3], ["switch", 2]])
    c = _client(result)
    out = c.entity_count("instance", group_by_attr="model_id")
    assert out == {"host": 3, "switch": 2}


def test_entity_count_with_permission_dict():
    result = FakeResultSet([("model_id", "model_id"), ("count", "count")], [["host", 1]])
    c = _client(result)
    out = c.entity_count(
        "instance", group_by_attr="model_id",
        format_permission_dict={4: [{"field": "inst_name", "type": "str[]", "value": ["h"]}]},
    )
    assert out == {"host": 1}


# --------------------------------------------------------------------------
# full_text / full_text_stats / full_text_by_model
# --------------------------------------------------------------------------


@pytest.fixture
def patch_exclude(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.graph.falkordb.ExcludeFieldsCache.get_exclude_fields",
        lambda: ["organization", "_creator"],
    )


def test_full_text(patch_exclude):
    nodes = [FakeNode(1, ["instance"], {"inst_name": "h1", "model_id": "host"})]
    c = _client(_entity_result(nodes))
    out = c.full_text("h1")
    assert out[0]["inst_name"] == "h1"


def test_full_text_no_exclude_cache(monkeypatch):
    monkeypatch.setattr("apps.cmdb.graph.falkordb.ExcludeFieldsCache.get_exclude_fields", lambda: [])
    c = _client()
    with pytest.raises(BaseAppException):
        c.full_text("h1")


def test_full_text_stats(patch_exclude):
    result = FakeResultSet([("model_id", "model_id"), ("count", "count")], [["host", 3], ["switch", 2]])
    c = _client(result)
    out = c.full_text_stats("h")
    assert out["total"] == 5
    assert {m["model_id"] for m in out["model_stats"]} == {"host", "switch"}


def test_full_text_by_model(patch_exclude):
    nodes = [FakeNode(1, ["instance"], {"inst_name": "h1", "model_id": "host"})]

    def result(cql, params):
        if "COUNT(n)" in cql:
            return FakeResultSet([("total", "total")], [[1]])
        return _entity_result(nodes)

    c = _client(result)
    out = c.full_text_by_model("h1", "host", page=1, page_size=10)
    assert out["total"] == 1
    assert out["data"][0]["inst_name"] == "h1"


def test_full_text_by_model_requires_model_id(patch_exclude):
    c = _client()
    with pytest.raises(BaseAppException):
        c.full_text_by_model("h", "")


def test_full_text_by_model_bad_page(patch_exclude):
    c = _client()
    with pytest.raises(BaseAppException):
        c.full_text_by_model("h", "host", page=0)


# --------------------------------------------------------------------------
# batch_save_entity
# --------------------------------------------------------------------------


def test_batch_save_entity_create_only():
    created = FakeNode(1, ["instance"], {"inst_name": "new"})
    c = _client(_entity_result([created]))
    result = c.batch_save_entity(
        label="instance",
        properties_list=[{"inst_name": "new"}],
        check_attr_map={},  # no unique key → all add
        exist_items=[],
    )
    # 返回 (add_results, update_results)
    add_results = result[0]
    assert add_results[0]["success"] is True


# --------------------------------------------------------------------------
# FalkorDBConnectionPool 线程安全（issue #3661）
# --------------------------------------------------------------------------


def test_connection_pool_singleton_under_concurrency(monkeypatch):
    """多线程并发构造 FalkorDBConnectionPool 只产生一个实例（__new__ 双检锁）。

    revert 双检锁后此测试有概率出现多个不同实例，即验证了修复点。
    """
    # 重置单例状态，使本测试独立于其他测试
    original_instance = FalkorDBConnectionPool._instance
    FalkorDBConnectionPool._instance = None

    instances = []
    barrier = threading.Barrier(20)

    def create_instance():
        barrier.wait()  # 所有线程同时冲入 __new__
        instances.append(FalkorDBConnectionPool())

    threads = [threading.Thread(target=create_instance) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 恢复原始状态
    FalkorDBConnectionPool._instance = original_instance

    unique_instances = set(id(i) for i in instances)
    assert len(unique_instances) == 1, (
        f"预期单例，但并发创建出 {len(unique_instances)} 个不同实例（连接泄漏）"
    )


def test_connection_pool_initialize_called_once_under_concurrency(monkeypatch):
    """多线程并发调用 get_connection 时，FalkorDB 连接只被创建一次（无连接泄漏）。

    通过 mock falkordb.FalkorDB 构造函数统计实际连接创建次数——
    revert _initialize 双检锁后此测试将断言 connection_count > 1，即验证了修复点。
    """
    import time
    from apps.cmdb.graph import falkordb as falkordb_module

    pool = FalkorDBConnectionPool()
    # 重置初始化状态
    original_initialized = pool._initialized
    original_client = pool._client
    original_graph = pool._graph
    pool._initialized = False
    pool._client = None
    pool._graph = None

    connection_count = [0]
    count_lock = threading.Lock()

    class FakeFalkorDB:
        def __init__(self, host, port, password):
            time.sleep(0.01)  # 拉长窗口，使无锁版本必然出现多次并发创建
            with count_lock:
                connection_count[0] += 1

        def select_graph(self, name):
            return object()

    # mock falkordb.FalkorDB，让真实的 _initialize 双检锁发挥作用
    monkeypatch.setattr(falkordb_module.falkordb, "FalkorDB", FakeFalkorDB)

    barrier = threading.Barrier(20)

    def call_get_connection():
        barrier.wait()
        pool.get_connection()

    threads = [threading.Thread(target=call_get_connection) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 恢复状态
    pool._initialized = original_initialized
    pool._client = original_client
    pool._graph = original_graph

    assert connection_count[0] == 1, (
        f"FalkorDB 连接应只被创建 1 次，实际创建了 {connection_count[0]} 次（出现连接泄漏）"
    )


def test_connection_pool_reinitializes_when_handles_missing(monkeypatch):
    """_initialized 与连接句柄不一致时，get_connection 应重新初始化。

    若只检查 _initialized，本测试会返回 (None, None)，复现 issue #3672 的状态错乱。
    """
    from apps.cmdb.graph import falkordb as falkordb_module

    pool = FalkorDBConnectionPool()
    original_initialized = pool._initialized
    original_client = pool._client
    original_graph = pool._graph
    pool._initialized = True
    pool._client = None
    pool._graph = None

    connection_count = [0]

    class FakeFalkorDB:
        def __init__(self, host, port, password):
            connection_count[0] += 1

        def select_graph(self, name):
            return object()

    monkeypatch.setattr(falkordb_module.falkordb, "FalkorDB", FakeFalkorDB)

    try:
        client, graph = pool.get_connection()
    finally:
        pool._initialized = original_initialized
        pool._client = original_client
        pool._graph = original_graph

    assert client is not None
    assert graph is not None
    assert connection_count[0] == 1


def test_execute_query_invalidates_pool_after_graph_error(monkeypatch):
    """图查询失败后连接池应失效，下一次 connect 可重新建立连接。

    若失败后仍保留 _initialized=True，后续请求会继续拿到坏连接。
    """
    from apps.cmdb.graph import falkordb as falkordb_module

    pool = FalkorDBConnectionPool()
    original_initialized = pool._initialized
    original_client = pool._client
    original_graph = pool._graph

    class BrokenGraph:
        def query(self, cql, params=None):
            raise ConnectionError("connection closed")

    class FakeFalkorDB:
        def select_graph(self, name):
            return FakeGraph(FakeResultSet([], []))

    pool._initialized = True
    pool._client = object()
    pool._graph = BrokenGraph()

    client = FalkorDBClient()
    client._pool = pool
    client._client = pool._client
    client._graph = pool._graph
    monkeypatch.setattr(falkordb_module.falkordb, "FalkorDB", FakeFalkorDB)

    try:
        with pytest.raises(ConnectionError):
            client._execute_query("MATCH (n) RETURN n")

        assert pool._initialized is False
        assert pool._client is None
        assert pool._graph is None

        assert client.connect() is True
        assert pool._initialized is True
        assert pool._client is not None
        assert pool._graph is not None
    finally:
        pool._initialized = original_initialized
        pool._client = original_client
        pool._graph = original_graph


# --------------------------------------------------------------------------
# Issue #3664 - 非参数化路径 key 校验（CQL 注入防护）
# --------------------------------------------------------------------------


def test_format_properties_rejects_malicious_key():
    """非参数化路径 format_properties 对恶意 key 应拒绝（CQL 注入防护）。
    若将修复 revert，此测试必然 pass 而 BaseAppException 不会被 raise。
    """
    malicious_key = "x}); DROP TABLE instance; MATCH (n"
    with pytest.raises(BaseAppException):
        FalkorDBClient.format_properties({malicious_key: "value"})


def test_format_properties_valid_key_passes():
    """合法 key 在非参数化路径仍正常工作。"""
    out = FalkorDBClient.format_properties({"inst_name": "host1", "count": 5})
    assert "inst_name:'host1'" in out
    assert "count:5" in out


def test_format_properties_set_rejects_malicious_key():
    """非参数化路径 format_properties_set 对恶意 key 应拒绝（CQL 注入防护）。
    若将修复 revert，此测试必然 pass 而 BaseAppException 不会被 raise。
    """
    c = _client()
    malicious_key = "name}=1 DETACH DELETE n //"
    with pytest.raises(BaseAppException):
        c.format_properties_set({malicious_key: "value"})


def test_format_properties_set_valid_key_passes():
    """合法 key 在 format_properties_set 仍正常工作。"""
    c = _client()
    out = c.format_properties_set({"inst_name": "host2", "count": 3})
    assert "n.inst_name='host2'" in out
    assert "n.count=3" in out
