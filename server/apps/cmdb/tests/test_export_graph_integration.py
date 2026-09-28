"""显式配置 CMDB_EXPORT_TEST_FALKORDB_URL 后，在独立临时图验证导出。

不使用应用的 FALKORDB_DATABASE，不读写业务图。连接失败应报错而非跳过。
"""

import os
from uuid import uuid4

import pytest
from falkordb import FalkorDB

from apps.cmdb.graph.export_query import export_association_queries
from apps.cmdb.graph.falkordb import FalkorDBClient


@pytest.fixture
def export_graph():
    url = os.getenv("CMDB_EXPORT_TEST_FALKORDB_URL")
    if not url:
        pytest.skip("未配置独立的导出图库集成测试连接")
    connection = FalkorDB.from_url(url)
    graph = connection.select_graph("cmdb_export_test_" + uuid4().hex)
    client = FalkorDBClient()
    client._graph = graph
    try:
        yield client, graph
    finally:
        graph.delete()


@pytest.mark.integration
def test_export_reads_legacy_edges_from_actual_endpoints_with_index(export_graph):
    client, graph = export_graph
    host, app, empty = (str(uuid4()) for _ in range(3))
    client.ensure_node_property_index("instance", "inst_uuid")
    graph.query(
        "CREATE (h:instance {inst_uuid: $host, model_id: 'host', inst_name: '主机', organization: [1]}), "
        "(a:instance {inst_uuid: $app, model_id: 'app', inst_name: '应用', organization: [2]}), "
        "(e:instance {inst_uuid: $empty, model_id: 'host', inst_name: '空关联', organization: [1]}), "
        "(h)-[:instance_association {model_asst_id: 'host_belong_app'}]->(a)",
        params={"host": host, "app": app, "empty": empty},
    )
    rows = client.query_export_associations("host", [host, empty], ["host_belong_app"])
    assert len(rows) == 1
    assert rows[0]["inst_uuid"] == host and rows[0]["peer_name"] == "应用"
    assert client.query_export_associations("host", [empty], ["host_belong_app"]) == []
    incoming = client.query_export_associations("app", [app], ["host_belong_app"])
    assert incoming[0]["peer_uuid"] == host
    assert client.query_export_associations("host", [host], ["unselected"]) == []
    for statement, params in export_association_queries("host", [host], ["host_belong_app"]):
        plan = str(graph.explain(statement, params=params))
        assert "Index Scan" in plan, plan
    instances, count = client.query_entity(
        "instance",
        [{"field": "model_id", "type": "str=", "value": "host"}],
        format_permission_dict={1: []},
        page={"skip": 0, "limit": 1},
        order="inst_uuid",
        include_count=False,
        fields=["inst_uuid", "inst_name"],
    )
    assert count is None and len(instances) == 1
    first = instances[0]["inst_uuid"]
    remaining, _ = client.query_entity(
        "instance",
        [{"field": "model_id", "type": "str=", "value": "host"}, {"field": "inst_uuid", "type": "str>", "value": first}],
        format_permission_dict={1: []},
        page={"skip": 0, "limit": 1},
        order="inst_uuid",
        include_count=False,
        fields=["inst_uuid", "inst_name"],
    )
    assert [first, remaining[0]["inst_uuid"]] == sorted([host, empty])
    other_team, _ = client.query_entity(
        "instance",
        [{"field": "model_id", "type": "str=", "value": "host"}],
        format_permission_dict={2: []},
        fields=["inst_uuid"],
    )
    assert other_team == []
