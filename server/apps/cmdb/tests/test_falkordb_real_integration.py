# -*- coding: utf-8 -*-
"""FalkorDBClient 真实图库集成测试（连 TEST_INFRA 上的 FalkorDB）。

与单元测试 test_falkordb_client.py（fake graph）互补：此处走真实 connect →
_execute_query → 结果格式化全链路，验证 CREATE/MATCH/SET/DELETE 在真实图库的
往返语义。无法连接时整体 skip，不破坏离线/CI 无图库环境。

每个测试用唯一 label（uuid 派生）隔离，结束 detach delete 清理，避免污染共享图。
"""
import os
import socket
import uuid

import pytest

from apps.cmdb.graph.falkordb import FalkorDBClient


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


@pytest.fixture
def label():
    """唯一标签 + 自动清理：标签合法（字母开头，无连字符）。"""
    name = "itest_" + uuid.uuid4().hex[:12]
    yield name
    # 清理：删掉该标签下所有节点
    try:
        client = FalkorDBClient()
        client.connect()
        client._graph.query(f"MATCH (n:{name}) DETACH DELETE n")
    except Exception:
        pass


def test_connect_returns_true():
    client = FalkorDBClient()
    assert client.connect() is True
    assert client._graph is not None


def test_create_and_query_entity_roundtrip(label):
    client = FalkorDBClient()
    client.connect()

    created = client.create_entity(
        label=label,
        properties={"inst_name": "host-real-1", "model_id": "host", "cpu": 8},
        check_attr_map={"is_only": {}, "is_required": {}},
        exist_items=[],
        operator="tester",
    )
    assert created["inst_name"] == "host-real-1"
    assert created["cpu"] == 8
    assert isinstance(created["_id"], int)

    # 真实 MATCH 往返（不分页时 count 为 None，按行数断言）
    rows, count = client.query_entity(label=label, params=[])
    assert len(rows) >= 1
    names = {r["inst_name"] for r in rows}
    assert "host-real-1" in names

    # 分页查询时才返回真实总数
    paged_rows, paged_count = client.query_entity(
        label=label, params=[], page={"skip": 0, "limit": 10}
    )
    assert paged_count >= 1


def test_query_entity_with_search_param(label):
    client = FalkorDBClient()
    client.connect()
    for name in ("alpha", "beta"):
        client.create_entity(
            label=label,
            properties={"inst_name": name, "model_id": "host"},
            check_attr_map={"is_only": {}, "is_required": {}},
            exist_items=[],
        )

    rows, _ = client.query_entity(
        label=label,
        params=[{"field": "inst_name", "type": "str=", "value": "alpha"}],
    )
    assert len(rows) == 1
    assert rows[0]["inst_name"] == "alpha"


def test_set_entity_properties_persists(label):
    client = FalkorDBClient()
    client.connect()
    created = client.create_entity(
        label=label,
        properties={"inst_name": "to-update", "model_id": "host", "status": "old"},
        check_attr_map={"is_only": {}, "is_required": {}},
        exist_items=[],
    )

    client.set_entity_properties(
        label=label,
        entity_ids=[created["_id"]],
        properties={"status": "new"},
        check_attr_map={"editable": {"status": "状态"}},
        exist_items=[],
        check=False,
    )

    rows, _ = client.query_entity(
        label=label,
        params=[{"field": "inst_name", "type": "str=", "value": "to-update"}],
    )
    assert rows[0]["status"] == "new"


def test_detach_delete_entity_removes_node(label):
    client = FalkorDBClient()
    client.connect()
    created = client.create_entity(
        label=label,
        properties={"inst_name": "doomed", "model_id": "host"},
        check_attr_map={"is_only": {}, "is_required": {}},
        exist_items=[],
    )

    client.detach_delete_entity(label, created["_id"])

    rows, count = client.query_entity(label=label, params=[])
    assert all(r["inst_name"] != "doomed" for r in rows)


def test_query_entity_by_id_roundtrip(label):
    client = FalkorDBClient()
    client.connect()
    created = client.create_entity(
        label=label,
        properties={"inst_name": "byid", "model_id": "host"},
        check_attr_map={"is_only": {}, "is_required": {}},
        exist_items=[],
    )
    fetched = client.query_entity_by_id(created["_id"])
    assert fetched["_id"] == created["_id"]
    assert fetched["inst_name"] == "byid"


def test_entity_count_grouped_real(label):
    client = FalkorDBClient()
    client.connect()
    for mid in ("host", "host", "switch"):
        client.create_entity(
            label=label,
            properties={"inst_name": uuid.uuid4().hex[:8], "model_id": mid},
            check_attr_map={"is_only": {}, "is_required": {}},
            exist_items=[],
        )
    # entity_count 默认对全 label 统计；这里只断言我们刚插入的分组计入
    counts = client.entity_count(label, group_by_attr="model_id")
    assert counts.get("host", 0) >= 2
    assert counts.get("switch", 0) >= 1
