# -*- coding: utf-8 -*-
"""FalkorDBClient 真实图库集成测试（扩展切片 cmdb-graph-svc）。

补 test_falkordb_real_integration.py 未覆盖的真实往返路径：边 CRUD、拓扑
（query_topo / query_topo_lite / query_network_topo）、batch_save_entity 的
新增+更新分支、批量删除、entity_count 带过滤参数、full_text 系列。

全部连 TEST_INFRA 上的真实 FalkorDB，走 connect → _execute_query → 结果格式化
全链路。每个测试用唯一 label（uuid 派生，字母开头无连字符）隔离，结束 detach
delete 清理。无法连接时整体 skip，不破坏离线/CI 无图库环境。
"""
import os
import socket
import uuid

import pydantic.root_model  # noqa: F401  预热，避免延迟导入抖动

import pytest

from apps.cmdb.display_field.cache import ExcludeFieldsCache
from apps.cmdb.graph.falkordb import FalkorDBClient
from apps.core.exceptions.base_app_exception import BaseAppException


def _falkordb_reachable() -> bool:
    host = os.getenv("FALKORDB_HOST", "")
    if not host:
        return False
    port = int(os.getenv("FALKORDB_PORT", "6379"))
    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _falkordb_reachable(),
    reason="FALKORDB_HOST 不可达，跳过真实图库集成测试",
)


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


@pytest.fixture
def client():
    c = FalkorDBClient()
    c.connect()
    return c


@pytest.fixture
def label():
    """唯一标签 + 自动清理。"""
    name = "gtest_" + uuid.uuid4().hex[:12]
    yield name
    try:
        c = FalkorDBClient()
        c.connect()
        c._graph.query(f"MATCH (n:{name}) DETACH DELETE n")
    except Exception:
        pass


def _mk_entity(client, label, name, model_id="host", **extra):
    props = {"inst_name": name, "model_id": model_id, **extra}
    return client.create_entity(
        label=label,
        properties=props,
        check_attr_map={"is_only": {}, "is_required": {}},
        exist_items=[],
        operator="tester",
    )


# --------------------------------------------------------------------------
# 边 CRUD 真实往返
# --------------------------------------------------------------------------


def test_create_edge_roundtrip_and_dedup(client, label):
    a = _mk_entity(client, label, "edge-a")
    b = _mk_entity(client, label, "edge-b")

    edge = client.create_edge(
        label="belong",
        a_id=a["_id"],
        a_label=label,
        b_id=b["_id"],
        b_label=label,
        properties={
            "model_asst_id": "host_belong_host",
            "asst_id": "belong",
            "src_inst_id": a["_id"],
            "dst_inst_id": b["_id"],
        },
        check_asst_key="model_asst_id",
    )
    assert isinstance(edge["_id"], int)
    assert edge["model_asst_id"] == "host_belong_host"

    # 同 a/b/check_val 重复创建应被拦截
    with pytest.raises(BaseAppException):
        client.create_edge(
            label="belong",
            a_id=a["_id"],
            a_label=label,
            b_id=b["_id"],
            b_label=label,
            properties={"model_asst_id": "host_belong_host"},
            check_asst_key="model_asst_id",
        )


def test_query_edge_and_by_id_and_set_and_delete(client, label):
    a = _mk_entity(client, label, "qe-a")
    b = _mk_entity(client, label, "qe-b")
    edge = client.create_edge(
        label="belong",
        a_id=a["_id"],
        a_label=label,
        b_id=b["_id"],
        b_label=label,
        properties={
            "model_asst_id": "m1",
            "asst_id": "belong",
            "src_model_id": "host",
            "dst_model_id": "host",
            "src_inst_id": a["_id"],
            "dst_inst_id": b["_id"],
        },
        check_asst_key="model_asst_id",
    )

    # query_edge by param
    edges = client.query_edge(
        label="belong",
        params=[{"field": "model_asst_id", "type": "str=", "value": "m1"}],
    )
    assert any(e["_id"] == edge["_id"] for e in edges)

    # query_edge_by_id
    fetched = client.query_edge_by_id(edge["_id"])
    assert fetched["_id"] == edge["_id"]
    assert fetched["model_asst_id"] == "m1"

    # set_edge_properties 真实持久化
    updated = client.set_edge_properties(edge["_id"], {"asst_id": "belong2", "weight": 5})
    assert updated["asst_id"] == "belong2"
    assert updated["weight"] == 5
    refetched = client.query_edge_by_id(edge["_id"])
    assert refetched["asst_id"] == "belong2"

    # delete_edge
    client.delete_edge(edge["_id"])
    after = client.query_edge(
        label="belong",
        params=[{"field": "model_asst_id", "type": "str=", "value": "m1"}],
    )
    assert all(e["_id"] != edge["_id"] for e in after)


def test_set_edge_properties_empty_raises(client):
    with pytest.raises(BaseAppException):
        client.set_edge_properties(1, {})


def test_batch_create_edge_mixed_success(client, label):
    a = _mk_entity(client, label, "bce-a")
    b = _mk_entity(client, label, "bce-b")
    results = client.batch_create_edge(
        label="belong",
        a_label=label,
        b_label=label,
        edge_list=[
            {"src_id": a["_id"], "dst_id": b["_id"], "model_asst_id": "bm1", "asst_id": "belong"},
            # 第二条缺 dst_id -> KeyError 转 failure 分支
            {"src_id": a["_id"], "model_asst_id": "bm2"},
        ],
        check_asst_key="model_asst_id",
    )
    assert results[0]["success"] is True
    assert results[1]["success"] is False
    assert "article 2 data" in results[1]["message"]


# --------------------------------------------------------------------------
# 拓扑真实往返：构建 a->b->c 链，验证 src/dst 树
# --------------------------------------------------------------------------


def _build_chain(client, label):
    a = _mk_entity(client, label, "topo-a")
    b = _mk_entity(client, label, "topo-b")
    c = _mk_entity(client, label, "topo-c")
    for src, dst in ((a, b), (b, c)):
        client.create_edge(
            label="belong",
            a_id=src["_id"],
            a_label=label,
            b_id=dst["_id"],
            b_label=label,
            properties={
                "model_asst_id": "host_belong_host",
                "asst_id": "belong",
                "src_inst_id": src["_id"],
                "dst_inst_id": dst["_id"],
            },
            check_asst_key="model_asst_id",
        )
    return a, b, c


def test_query_topo_full_chain(client, label):
    a, b, c = _build_chain(client, label)
    topo = client.query_topo(label=label, inst_id=a["_id"])
    assert "src_result" in topo and "dst_result" in topo
    src = topo["src_result"]
    assert src["_id"] == a["_id"]
    # a 作为源，子孙含 b（及更深 c）
    child_ids = {child["_id"] for child in src["children"]}
    assert b["_id"] in child_ids


def test_query_topo_lite_depth_limit(client, label):
    a, b, c = _build_chain(client, label)
    # depth=1 => a 的下钻被截断，has_more 应为 True
    topo = client.query_topo_lite(label=label, inst_id=a["_id"], depth=1)
    src = topo["src_result"]
    assert src["_id"] == a["_id"]
    assert src.get("has_more") is True
    assert src["children"] == []

    # depth=3 => 能下钻到 b
    topo3 = client.query_topo_lite(label=label, inst_id=a["_id"], depth=3)
    child_ids = {child["_id"] for child in topo3["src_result"]["children"]}
    assert b["_id"] in child_ids


def test_query_topo_lite_exclude_ids(client, label):
    a, b, c = _build_chain(client, label)
    # 排除 b，则 a 的 src 树里不应出现 b
    topo = client.query_topo_lite(label=label, inst_id=a["_id"], depth=3, exclude_ids=[b["_id"]])
    child_ids = {child["_id"] for child in topo["src_result"]["children"]}
    assert b["_id"] not in child_ids


def test_query_topo_missing_node_returns_empty_tree(client, label):
    a = _mk_entity(client, label, "lonely")
    # 孤立节点无任何边：format_topo 的 start 不在结果集 -> {}
    topo = client.query_topo(label=label, inst_id=a["_id"])
    assert topo["src_result"] == {}
    assert topo["dst_result"] == {}


def test_query_network_topo_real(client, label):
    """构建 dev1 - if1 -[connect]- if2 - dev2 的网络拓扑场景。"""
    dev1 = _mk_entity(client, label, "dev1", model_id="switch")
    dev2 = _mk_entity(client, label, "dev2", model_id="switch")
    if1 = _mk_entity(client, label, "if1", model_id="interface")
    if2 = _mk_entity(client, label, "if2", model_id="interface")

    belong = "interface_belong_switch"
    connect = "interface_connect_interface"

    def edge(a, b, masst, asst):
        client.create_edge(
            label="connect" if asst == "connect" else "belong",
            a_id=a["_id"], a_label=label, b_id=b["_id"], b_label=label,
            properties={
                "model_asst_id": masst, "asst_id": asst,
                "src_inst_id": a["_id"], "dst_inst_id": b["_id"],
            },
            check_asst_key="model_asst_id",
        )

    # if -> dev (belong)
    edge(if1, dev1, belong, "belong")
    edge(if2, dev2, belong, "belong")
    # if1 - if2 connect
    edge(if1, if2, connect, "connect")

    rows = client.query_network_topo(inst_id=dev1["_id"], belong_asst_id=belong)
    assert isinstance(rows, list)
    # 至少应找到 dev1 的对端 dev2
    peers = {r["peer_id"] for r in rows}
    assert dev2["_id"] in peers
    target = next(r for r in rows if r["peer_id"] == dev2["_id"])
    assert target["dev_id"] == dev1["_id"]
    assert target["dev_name"] == "dev1"
    assert target["peer_name"] == "dev2"


# --------------------------------------------------------------------------
# topo 配置 / convert_to_cypher_match / query_topo_test_config
# --------------------------------------------------------------------------


def test_get_topo_config_loads_real_file(client):
    cfg = client.get_topo_config()
    assert isinstance(cfg, dict)
    # 仓库内 topo_config.json 含 k8s_cluster 配置
    assert "k8s_cluster" in cfg
    assert "src" in cfg["k8s_cluster"]


def test_convert_to_cypher_match_default_when_no_config(client):
    # 未配置的 model_id -> 走默认 MATCH 路径
    sql = client.convert_to_cypher_match(":instance", "no_such_model", "AND ID(n) = $inst_id", dst=True)
    assert "MATCH p=" in sql
    assert "RETURN p" in sql
    assert "no_such_model" not in sql


def test_convert_to_cypher_match_uses_configured_path(client):
    # k8s_cluster 有 src 配置 -> 走配置拼接分支
    sql = client.convert_to_cypher_match(":instance", "k8s_cluster", "AND ID(n) = $inst_id", dst=False)
    assert "k8s_cluster" in sql
    assert "k8s_namespace" in sql
    assert "k8scluster_group_namespace" in sql
    assert sql.startswith("MATCH p=")


def test_query_topo_test_config_real_chain(client, label):
    a, b, c = _build_chain(client, label)
    # model_id 无配置 -> 走默认路径，但仍真实执行查询并格式化
    topo = client.query_topo_test_config(label=label, inst_id=a["_id"], model_id="host")
    assert "src_result" in topo and "dst_result" in topo
    assert topo["src_result"].get("_id") == a["_id"]


# --------------------------------------------------------------------------
# 非参数化分支（ENABLE_PARAMETERIZATION=False）真实往返
# --------------------------------------------------------------------------


def _nonparam_client():
    c = FalkorDBClient()
    c.ENABLE_PARAMETERIZATION = False
    c.connect()
    return c


def test_nonparam_create_query_set_delete_roundtrip(label):
    c = _nonparam_client()
    created = c.create_entity(
        label=label,
        properties={"inst_name": "np-1", "model_id": "host", "cpu": 4},
        check_attr_map={"is_only": {}, "is_required": {}},
        exist_items=[],
        operator="tester",
    )
    assert created["inst_name"] == "np-1"

    rows, _ = c.query_entity(
        label=label,
        params=[{"field": "inst_name", "type": "str=", "value": "np-1"}],
    )
    assert rows and rows[0]["cpu"] == 4

    c.set_entity_properties(
        label=label,
        entity_ids=[created["_id"]],
        properties={"cpu": 16},
        check_attr_map={"editable": {"cpu": "CPU"}},
        exist_items=[],
        check=False,
    )
    rows2, _ = c.query_entity(
        label=label,
        params=[{"field": "inst_name", "type": "str=", "value": "np-1"}],
    )
    assert rows2[0]["cpu"] == 16

    c.detach_delete_entity(label, created["_id"])
    rows3, _ = c.query_entity(label=label, params=[])
    assert all(r["inst_name"] != "np-1" for r in rows3)


def test_nonparam_create_edge_and_topo(label):
    c = _nonparam_client()
    a = c.create_entity(label=label, properties={"inst_name": "npe-a", "model_id": "host"},
                        check_attr_map={"is_only": {}, "is_required": {}}, exist_items=[])
    b = c.create_entity(label=label, properties={"inst_name": "npe-b", "model_id": "host"},
                        check_attr_map={"is_only": {}, "is_required": {}}, exist_items=[])
    edge = c.create_edge(
        label="belong", a_id=a["_id"], a_label=label, b_id=b["_id"], b_label=label,
        properties={
            "model_asst_id": "npm", "asst_id": "belong",
            "src_model_id": "host", "dst_model_id": "host",
            "src_inst_id": a["_id"], "dst_inst_id": b["_id"],
        },
        check_asst_key="model_asst_id",
    )
    assert isinstance(edge["_id"], int)

    topo = c.query_topo(label=label, inst_id=a["_id"])
    child_ids = {child["_id"] for child in topo["src_result"]["children"]}
    assert b["_id"] in child_ids


def test_nonparam_full_text(ft_token, patched_exclude):
    c = _nonparam_client()
    _mk_instance(c, ft_token + "-np")
    rows = c.full_text(ft_token)
    names = {r.get("inst_name") for r in rows}
    assert any(ft_token in (n or "") for n in names)

    # case_sensitive 精确分支（非参数化）
    exact = c.full_text(ft_token + "-np", case_sensitive=True)
    assert any((r.get("inst_name") == ft_token + "-np") for r in exact)


# --------------------------------------------------------------------------
# full_text_by_model 参数校验 + 缓存缺失
# --------------------------------------------------------------------------


def test_full_text_by_model_validation_errors(client):
    with pytest.raises(BaseAppException):
        client.full_text_by_model("x", model_id="")
    with pytest.raises(BaseAppException):
        client.full_text_by_model("x", model_id="host", page=0)
    with pytest.raises(BaseAppException):
        client.full_text_by_model("x", model_id="host", page_size=0)
    with pytest.raises(BaseAppException):
        client.full_text_by_model("x", model_id="host", page_size=101)


def test_full_text_by_model_no_cache_raises(client, monkeypatch):
    monkeypatch.setattr(ExcludeFieldsCache, "get_exclude_fields", classmethod(lambda cls: []))
    with pytest.raises(BaseAppException):
        client.full_text_by_model("x", model_id="host")


def test_full_text_stats_no_cache_raises(client, monkeypatch):
    monkeypatch.setattr(ExcludeFieldsCache, "get_exclude_fields", classmethod(lambda cls: []))
    with pytest.raises(BaseAppException):
        client.full_text_stats("x")


# --------------------------------------------------------------------------
# batch_save_entity 真实新增 + 更新分支
# --------------------------------------------------------------------------


def test_batch_save_entity_create_and_update(client, label):
    # 先建一个已存在节点（唯一键 inst_name=keep）
    existing = _mk_entity(client, label, "keep", status="old")

    # ModelConstraintKey.unique.value == "is_only"，唯一键须放在 is_only 下
    check_attr_map = {
        "is_only": {"inst_name": "名称"},
        "is_required": {},
        "editable": {"status": "状态"},
    }
    exist_items = [{"_id": existing["_id"], "inst_name": "keep", "model_id": "host"}]

    add_results, update_results = client.batch_save_entity(
        label=label,
        properties_list=[
            {"inst_name": "keep", "model_id": "host", "status": "new"},  # 命中已存在 -> 更新
            {"inst_name": "fresh", "model_id": "host", "status": "x"},   # 新增
        ],
        check_attr_map=check_attr_map,
        exist_items=exist_items,
        operator="tester",
    )
    # keep 命中已存在 -> 走更新分支；fresh -> 新增分支
    assert any(r.get("success") for r in update_results)
    assert any(r.get("success") and r["data"]["inst_name"] == "fresh" for r in add_results)

    rows, _ = client.query_entity(
        label=label,
        params=[{"field": "inst_name", "type": "str=", "value": "keep"}],
    )
    assert rows and rows[0]["status"] == "new"

    fresh, _ = client.query_entity(
        label=label,
        params=[{"field": "inst_name", "type": "str=", "value": "fresh"}],
    )
    assert fresh and fresh[0]["status"] == "x"


def test_batch_save_entity_no_unique_key_all_create(client, label):
    add_results, update_results = client.batch_save_entity(
        label=label,
        properties_list=[
            {"inst_name": "nu1", "model_id": "host"},
            {"inst_name": "nu2", "model_id": "host"},
        ],
        check_attr_map={"is_only": {}, "is_required": {}},
        exist_items=[],
    )
    # 无唯一键 -> 全部走新增分支，无更新
    assert update_results == []
    assert all(r.get("success") for r in add_results)
    rows, _ = client.query_entity(label=label, params=[])
    names = {r["inst_name"] for r in rows}
    assert {"nu1", "nu2"} <= names


def test_batch_delete_entity_real(client, label):
    e1 = _mk_entity(client, label, "del1")
    e2 = _mk_entity(client, label, "del2")
    e3 = _mk_entity(client, label, "keep3")

    client.batch_delete_entity(label, [e1["_id"], e2["_id"]])

    rows, _ = client.query_entity(label=label, params=[])
    names = {r["inst_name"] for r in rows}
    assert "keep3" in names
    assert "del1" not in names and "del2" not in names


# --------------------------------------------------------------------------
# query_entity：权限字典 / 排序 / 分页
# --------------------------------------------------------------------------


def test_query_entity_permission_dict_and_order(client, label):
    # organization 为 list（权限过滤用 ALL(x IN $list WHERE x IN n.organization)）
    _mk_entity(client, label, "q-a", organization=["org1"], rank=2)
    _mk_entity(client, label, "q-b", organization=["org1"], rank=1)
    _mk_entity(client, label, "q-c", organization=["org2"], rank=9)

    rows, count = client.query_entity(
        label=label,
        params=[],
        format_permission_dict={"org1": []},
        order="rank",
        order_type="ASC",
        page={"skip": 0, "limit": 10},
    )
    names = {r["inst_name"] for r in rows}
    # 只应命中 org1 的两条
    assert "q-a" in names and "q-b" in names
    assert "q-c" not in names
    assert count >= 2
    # 排序生效：rank 升序，q-b(1) 在 q-a(2) 前
    ranked = [r["inst_name"] for r in rows if r["inst_name"] in ("q-a", "q-b")]
    assert ranked == ["q-b", "q-a"]


# --------------------------------------------------------------------------
# 表格字段序列化/反序列化真实往返（_serialize/_deserialize_table_fields）
# --------------------------------------------------------------------------


def test_table_field_serialize_roundtrip(client):
    """instance + table 类型 attr：list 落库为 JSON 串，查询回来反序列化为 list。"""
    token = "tbl" + uuid.uuid4().hex[:8]
    attrs = [
        {"attr_id": "ports", "attr_type": "table", "attr_name": "端口表"},
        {"attr_id": "inst_name", "attr_type": "str", "attr_name": "名称"},
    ]
    table_value = [{"port": 80, "proto": "tcp"}, {"port": 443, "proto": "tcp"}]
    created = client.create_entity(
        label="instance",
        properties={"inst_name": token, "model_id": "host", "ports": table_value},
        check_attr_map={"is_only": {}, "is_required": {}},
        exist_items=[],
        operator="tester",
        attrs=attrs,
    )
    try:
        # 落库形态：ports 已是 JSON 字符串（_serialize_table_fields 生效）
        raw = client.query_entity_by_id(created["_id"])
        assert isinstance(raw["ports"], str)

        # 反序列化：把真实查询结果喂给 _deserialize -> list 还原
        restored = client._deserialize_table_fields_in_result_list([dict(raw)], attrs=attrs)
        assert isinstance(restored[0]["ports"], list)
        assert restored[0]["ports"] == table_value

        # 反序列化坏数据 -> 回退空列表
        bad = client._deserialize_table_fields_in_result_list(
            [{"ports": "not-json"}], attrs=attrs
        )
        assert bad[0]["ports"] == []
    finally:
        client.detach_delete_entity("instance", created["_id"])


# --------------------------------------------------------------------------
# full_text 系列带 created / inst_name / permission 过滤
# --------------------------------------------------------------------------


def test_full_text_with_created_and_inst_name_filter(client, ft_token, patched_exclude):
    a = _mk_instance(client, ft_token + "-mine")
    # 改 _creator 让其归属特定用户
    client.set_entity_properties(
        label="instance", entity_ids=[a["_id"]],
        properties={"_creator": "owner-x"},
        check_attr_map={}, exist_items=[], check=False,
    )
    _mk_instance(client, ft_token + "-other")

    rows = client.full_text(
        ft_token,
        created="owner-x",
        inst_name_params=f"n.inst_name CONTAINS '{ft_token}'",
    )
    names = {r.get("inst_name") for r in rows}
    assert ft_token + "-mine" in names
    assert ft_token + "-other" not in names


def test_full_text_stats_with_created_filter(client, ft_token, patched_exclude):
    a = _mk_instance(client, ft_token + "-s1", model_id="host")
    client.set_entity_properties(
        label="instance", entity_ids=[a["_id"]],
        properties={"_creator": "owner-y"},
        check_attr_map={}, exist_items=[], check=False,
    )
    _mk_instance(client, ft_token + "-s2", model_id="switch")

    stats = client.full_text_stats(ft_token, created="owner-y")
    model_map = {m["model_id"]: m["count"] for m in stats["model_stats"]}
    assert model_map.get("host", 0) >= 1
    # owner-y 没有 switch 实例
    assert "switch" not in model_map


# --------------------------------------------------------------------------
# entity_count 带过滤参数
# --------------------------------------------------------------------------


def test_entity_count_with_filter_params(client, label):
    for name, region in (("c1", "north"), ("c2", "north"), ("c3", "south")):
        _mk_entity(client, label, name, region=region)

    counts = client.entity_count(
        label,
        group_by_attr="region",
        params=[{"field": "region", "type": "str=", "value": "north"}],
    )
    assert counts.get("north", 0) >= 2
    assert "south" not in counts


# --------------------------------------------------------------------------
# full_text 系列（真实 MATCH，monkeypatch 排除字段缓存）
# --------------------------------------------------------------------------


@pytest.fixture
def patched_exclude(monkeypatch):
    monkeypatch.setattr(
        ExcludeFieldsCache,
        "get_exclude_fields",
        classmethod(lambda cls: ["_id", "_creator", "organization"]),
    )


@pytest.fixture
def ft_token():
    """full_text 走固定 label=instance，用唯一 token 隔离 + 收尾清理。"""
    token = "ft" + uuid.uuid4().hex[:8]
    yield token
    try:
        c = FalkorDBClient()
        c.connect()
        c._graph.query(
            "MATCH (n:instance) WHERE n.inst_name CONTAINS $t DETACH DELETE n",
            {"t": token},
        )
    except Exception:
        pass


def _mk_instance(client, name, model_id="host"):
    return client.create_entity(
        label="instance",
        properties={"inst_name": name, "model_id": model_id},
        check_attr_map={"is_only": {}, "is_required": {}},
        exist_items=[],
        operator="tester",
    )


def test_full_text_requires_exclude_cache(client, monkeypatch):
    monkeypatch.setattr(
        ExcludeFieldsCache, "get_exclude_fields", classmethod(lambda cls: [])
    )
    with pytest.raises(BaseAppException):
        client.full_text("anything")


def test_full_text_matches_real_instances(client, ft_token, patched_exclude):
    _mk_instance(client, ft_token + "-aaa")
    _mk_instance(client, "unrelated-bbb")

    rows = client.full_text(ft_token)
    names = {r.get("inst_name") for r in rows}
    assert any(ft_token in (n or "") for n in names)
    assert "unrelated-bbb" not in names


def test_full_text_stats_aggregates(client, ft_token, patched_exclude):
    _mk_instance(client, ft_token + "-1", model_id="host")
    _mk_instance(client, ft_token + "-2", model_id="host")
    _mk_instance(client, ft_token + "-3", model_id="switch")

    stats = client.full_text_stats(ft_token)
    assert "total" in stats and "model_stats" in stats
    assert stats["total"] >= 3
    model_map = {m["model_id"]: m["count"] for m in stats["model_stats"]}
    assert model_map.get("host", 0) >= 2
    assert model_map.get("switch", 0) >= 1


def test_full_text_by_model_filters(client, ft_token, patched_exclude):
    _mk_instance(client, ft_token + "-h1", model_id="host")
    _mk_instance(client, ft_token + "-s1", model_id="switch")

    res = client.full_text_by_model(ft_token, model_id="host")
    # 返回分页结构
    assert "data" in res
    data = res["data"]
    # 命中本 token 的都应是 host 模型
    hits = [item for item in data if ft_token in (item.get("inst_name") or "")]
    assert hits
    for item in hits:
        assert item.get("model_id") == "host"


def test_full_text_case_sensitive_exact(client, ft_token, patched_exclude):
    _mk_instance(client, ft_token)

    # case_sensitive=True 精确匹配整值
    rows = client.full_text(ft_token, case_sensitive=True)
    names = {r.get("inst_name") for r in rows}
    assert ft_token in names
