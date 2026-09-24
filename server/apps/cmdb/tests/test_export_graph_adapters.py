"""导出关联的参数绑定、工作集边界和两种图库驱动结果契约。"""

from types import SimpleNamespace

import pytest

from apps.cmdb.graph.export_query import EXPORT_BATCH_SIZE
from apps.cmdb.graph.falkordb import FalkorDBClient
from apps.cmdb.graph.neo4j import Neo4jClient

UUID = "123e4567-e89b-42d3-a456-000000000001"


@pytest.mark.parametrize("driver", [FalkorDBClient, Neo4jClient])
def test_associations_are_anchored_at_nodes_and_return_named_scalars(driver):
    client = driver.__new__(driver)
    calls = []
    expected = dict(
        inst_uuid=UUID, model_asst_id="host_belong_app", peer_uuid=UUID, peer_name="应用", edge_id=9, src_model_id="host", dst_model_id="app"
    )

    def execute(statement, params=None, **kwargs):
        calls.append((statement, params or kwargs))
        if driver is FalkorDBClient:
            return SimpleNamespace(result_set=[list(expected.values())])
        return [expected]

    if driver is FalkorDBClient:
        client._execute_query = execute
    else:
        client.session = SimpleNamespace(run=execute)
    sentinel = "host' OR 1=1"
    result = client.query_export_associations(sentinel, [UUID], ["host_belong_app"])
    assert result == [expected, expected]
    assert len(calls) == 2
    for statement, params in calls:
        assert "MATCH (n:instance) WHERE n.inst_uuid IN $inst_uuids" in statement
        assert "r.model_asst_id IN $association_ids" in statement
        assert "r.src_inst_uuid" not in statement and "r.src_model_id" not in statement
        assert "RETURN p" not in statement  # 不传回完整节点/关系属性。
        assert sentinel not in statement
        assert params == {"model_id": sentinel, "inst_uuids": [UUID], "association_ids": ["host_belong_app"]}
    assert "(n)-[r:instance_association]->" in calls[0][0]
    assert "(n)<-[r:instance_association]-" in calls[1][0]


@pytest.mark.parametrize("driver", [FalkorDBClient, Neo4jClient])
def test_empty_scope_never_becomes_unfiltered_query(driver):
    client = driver.__new__(driver)
    assert client.query_export_associations("host", [], ["host_belong_app"]) == []
    assert client.query_export_associations("host", [UUID], []) == []
    with pytest.raises(ValueError, match="批次上限"):
        client.query_export_associations("host", [UUID] * (EXPORT_BATCH_SIZE + 1), ["host_belong_app"])


@pytest.mark.parametrize("driver", [FalkorDBClient, Neo4jClient])
def test_projected_instance_page_keeps_permissions_and_cursor_parameterized(driver):
    client = driver() if driver is FalkorDBClient else driver.__new__(driver)
    calls = []

    def execute(statement, params=None, **kwargs):
        calls.append((statement, params or kwargs))
        row = {"_id": 1, "inst_uuid": UUID, "inst_name": "host-1", "cloud": "1"}
        return SimpleNamespace(result_set=[[row]]) if driver is FalkorDBClient else [[row]]

    if driver is FalkorDBClient:
        client._execute_query = execute
    else:
        client.session = SimpleNamespace(run=execute)
    rows, count = client.query_entity(
        "instance",
        [{"field": "model_id", "type": "str=", "value": "host"}, {"field": "inst_uuid", "type": "str>", "value": UUID}],
        format_permission_dict={2: []},
        page={"skip": 0, "limit": 500},
        order="inst_uuid",
        include_count=False,
        fields=["inst_uuid", "inst_name", "cloud"],
    )
    assert rows == [{"_id": 1, "inst_uuid": UUID, "inst_name": "host-1", "cloud": 1}]
    assert count is None
    assert len(calls) == 1  # 不附带 count 查询。
    statement, params = calls[0]
    assert "n.organization" in statement
    assert "n.inst_uuid > $" in statement
    assert UUID not in statement and UUID in params.values()
    assert [2] in params.values()
    assert "RETURN {_id: ID(n), inst_uuid: n.inst_uuid, inst_name: n.inst_name, cloud: n.cloud}" in statement
    assert "ORDER BY n.inst_uuid ASC SKIP 0 LIMIT 500" in statement


def test_projection_rejects_untrusted_identifiers():
    from apps.cmdb.graph.export_query import entity_projection
    from apps.core.exceptions.base_app_exception import BaseAppException

    with pytest.raises(BaseAppException):
        entity_projection(["name) RETURN n //"])


def test_uuid_cursor_formatters_bind_or_escape_values():
    from apps.cmdb.graph.format_type import FORMAT_TYPE, FORMAT_TYPE_PARAMS, ParameterCollector

    value = "value'\\tail"
    param = {"field": "inst_uuid", "type": "str>", "value": value}
    collector = ParameterCollector()
    query = FORMAT_TYPE_PARAMS["str>"](param, collector)
    assert value not in query
    assert list(collector.get_params().values()) == [value]
    assert FORMAT_TYPE["str>"](param) == "n.inst_uuid > 'value\\'\\\\tail'"
