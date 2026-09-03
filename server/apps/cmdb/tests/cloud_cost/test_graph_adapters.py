"""FalkorDB / Neo4j 云成本查询 adapter 契约。"""

from apps.cmdb.graph.falkordb import FalkorDBClient
from apps.cmdb.graph.neo4j import Neo4jClient
from apps.cmdb.services.cloud_cost.query import CloudCostQueryPlan


def _plan():
    permission = {1: {"inst_names": []}}
    return CloudCostQueryPlan(
        kind="summary",
        bill_permission_map=permission,
        log_permission_map=permission,
    )


class _FalkorResult:
    header = [[1, "total_cost"], [1, "instance_count"]]
    result_set = [[100001.0, 100001]]


def test_falkordb_adapter_returns_named_scalar_rows(monkeypatch):
    client = FalkorDBClient.__new__(FalkorDBClient)
    captured = {}

    def execute(statement, params=None, timeout=None):
        captured.update(statement=statement, params=params, timeout=timeout)
        return _FalkorResult()

    monkeypatch.setattr(client, "_execute_query", execute)

    assert client.query_cloud_cost(_plan()) == [{"total_cost": 100001.0, "instance_count": 100001}]
    assert "LIMIT" not in captured["statement"]
    assert captured["params"]["bill_model"] == "resource_bill"
    assert captured["timeout"] == 30000


class _NeoSession:
    def __init__(self):
        self.statement = ""
        self.params = {}

    def run(self, statement, **params):
        self.statement = statement
        self.params = params
        return [{"total_cost": 100001.0, "instance_count": 100001}]


def test_neo4j_adapter_returns_same_named_scalar_rows():
    client = Neo4jClient.__new__(Neo4jClient)
    client.session = _NeoSession()

    assert client.query_cloud_cost(_plan()) == [{"total_cost": 100001.0, "instance_count": 100001}]
    assert "coalesce(bill.organization, [])" in str(client.session.statement)
    assert client.session.statement.timeout == 30
    assert client.session.params["log_model"] == "transaction_log"
