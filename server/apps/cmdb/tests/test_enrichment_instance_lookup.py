"""告警丰富按 UUID / monitor_id 定位实例，并保持组织过滤。"""

import pytest

from apps.cmdb.nats import nats as N
from apps.cmdb.services.instance import InstanceManage

UUID = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"


@pytest.mark.unit
def test_search_instances_batch_by_uuid_drops_other_org(monkeypatch):
    def query(inst_uuids, *, fields=None):
        assert inst_uuids == [UUID]
        return [{"inst_uuid": UUID, "organization": [2], "owner": "other", "_id": 1, "_labels": [], "permission": {}}]

    monkeypatch.setattr(N.InstanceManage, "query_entity_by_uuids", query)

    assert N.search_instances_batch({"protocol_version": "2", "inst_uuids": [UUID], "organization_ids": [7]}) == {}


@pytest.mark.unit
def test_search_instances_batch_by_uuid_returns_same_org(monkeypatch):
    monkeypatch.setattr(
        N.InstanceManage,
        "query_entity_by_uuids",
        lambda inst_uuids, *, fields=None: [{"inst_uuid": UUID, "organization": [7], "owner": "alice", "_id": 1, "_labels": ["x"], "permission": {}}],
    )

    result = N.search_instances_batch({"protocol_version": "2", "inst_uuids": [UUID.upper()], "organization_ids": [7]})

    assert result == {UUID: {"inst_uuid": UUID, "organization": [7], "owner": "alice"}}


@pytest.mark.unit
def test_search_instances_batch_by_monitor_id_prefers_same_org(monkeypatch):
    monkeypatch.setattr(
        N.InstanceManage,
        "search_inst_by_monitor_ids",
        lambda monitor_ids: {
            "0001": [
                {"monitor_id": "0001", "organization": [9], "owner": "no"},
                {"monitor_id": "0001", "organization": [7], "owner": "yes"},
            ]
        },
    )

    result = N.search_instances_batch({"protocol_version": "2", "monitor_ids": ["0001"], "organization_ids": [7]})

    assert result["0001"]["owner"] == "yes"


@pytest.mark.unit
def test_search_inst_by_monitor_ids_queries_attribute(monkeypatch):
    class _Graph:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def query_entity(self, label, params):
            self.params = params
            return ([{"monitor_id": "0001", "organization": [7]}], 1)

    graph = _Graph()
    monkeypatch.setattr("apps.cmdb.services.instance.GraphClient", lambda: graph)

    result = InstanceManage.search_inst_by_monitor_ids(["0001", " 0001", ""])

    assert graph.params == [{"field": "monitor_id", "type": "str[]", "value": ["0001"]}]
    assert result["0001"][0]["organization"] == [7]
