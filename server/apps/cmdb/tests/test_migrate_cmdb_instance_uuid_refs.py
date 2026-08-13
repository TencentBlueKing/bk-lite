from uuid import UUID

import pytest
from django.core.management.base import CommandError

from apps.cmdb.management.commands.migrate_cmdb_instance_uuid_refs import Command


class _Graph:
    def __init__(self, entities, edges):
        self.entities = entities
        self.edges = edges
        self.node_updates = []
        self.edge_sets = []
        self.edge_removals = []
        self.indexes = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def query_entity(self, _label, params, page=None, include_count=False):
        entities = self.entities
        cursor = next((item["value"] for item in params if item.get("type") == "id>"), None)
        if cursor is not None:
            entities = [item for item in entities if item["_id"] > cursor]
        if page is None:
            return entities, None
        start = page["skip"]
        end = start + page["limit"]
        return entities[start:end], None

    def batch_update_node_property_values(self, label, field, values):
        self.node_updates.append((label, field, values))
        value_by_id = {item["id"]: item["value"] for item in values}
        for entity in self.entities:
            if entity["_id"] in value_by_id:
                entity[field] = value_by_id[entity["_id"]]

    def query_edge(self, _label, _params, return_entity):
        return self.edges

    def set_edge_properties(self, edge_id, properties):
        self.edge_sets.append((edge_id, properties))
        for item in self.edges:
            edge = item.get("edge") or item
            if edge.get("_id") == edge_id:
                edge.update(properties)

    def remove_edge_properties(self, edge_ids, attrs):
        self.edge_removals.append((edge_ids, attrs))
        for item in self.edges:
            edge = item.get("edge") or item
            if edge.get("_id") in edge_ids:
                for attr in attrs:
                    edge.pop(attr, None)

    def ensure_node_property_index(self, label, field):
        self.indexes.append((label, field))


def _stats():
    return {
        "graph_instance_scanned": 0,
        "graph_uuid_added": 0,
        "graph_relation_scanned": 0,
        "graph_relation_uuid_set": 0,
        "graph_relation_digit_removed": 0,
        "graph_index_ensured": 0,
    }


def test_clean_graph_adds_uuid_sets_endpoints_and_removes_digit_ids(monkeypatch):
    existing_uuid = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
    entities = [
        {"_id": 1, "model_id": "host"},
        {"_id": 2, "model_id": "host", "inst_uuid": existing_uuid},
    ]
    edges = [
        {
            "edge": {
                "_id": 9,
                "model_asst_id": "host_run_host",
                "src_inst_id": 1,
                "dst_inst_id": 2,
            },
            "src": entities[0],
            "dst": entities[1],
        }
    ]
    graph = _Graph(entities, edges)
    monkeypatch.setattr(
        "apps.cmdb.management.commands.migrate_cmdb_instance_uuid_refs.GraphClient",
        lambda: graph,
    )
    command = Command()
    command._graph_uuid_by_id = {}
    monkeypatch.setattr(command, "_stage_cursor", lambda stage: (0, False))
    monkeypatch.setattr(command, "_save_stage", lambda *args, **kwargs: None)
    stats = _stats()

    command._clean_graph(batch_size=1, dry_run=False, stats=stats)

    assert UUID(entities[0]["inst_uuid"]).version == 4
    assert command._graph_uuid_by_id[2] == existing_uuid
    assert graph.edge_sets == [
        (
            9,
            {
                "src_inst_uuid": entities[0]["inst_uuid"],
                "dst_inst_uuid": existing_uuid,
            },
        )
    ]
    assert graph.edge_removals == [([9], ["src_inst_id", "dst_inst_id"])]
    assert graph.indexes == [("instance", "inst_uuid")]
    assert stats["graph_uuid_added"] == 1
    assert stats["graph_relation_uuid_set"] == 1
    assert stats["graph_relation_digit_removed"] == 1


def test_clean_graph_resolves_same_model_endpoints_from_digit_ids(monkeypatch):
    entities = [
        {"_id": 1, "model_id": "host", "inst_uuid": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"},
        {"_id": 2, "model_id": "host", "inst_uuid": "73e4a531-b6bb-43cc-9eae-8eb8a09f795e"},
    ]
    edges = [
        {
            "edge": {
                "_id": 188,
                "model_asst_id": "host_run_host",
                "src_inst_id": 1,
                "dst_inst_id": 2,
            },
            "src": {},
            "dst": {},
        }
    ]
    graph = _Graph(entities, edges)
    monkeypatch.setattr(
        "apps.cmdb.management.commands.migrate_cmdb_instance_uuid_refs.GraphClient",
        lambda: graph,
    )
    command = Command()
    command._graph_uuid_by_id = {}
    monkeypatch.setattr(command, "_stage_cursor", lambda stage: (0, False))
    monkeypatch.setattr(command, "_save_stage", lambda *args, **kwargs: None)

    command._clean_graph(batch_size=10, dry_run=False, stats=_stats())

    assert graph.edge_sets == [
        (
            188,
            {
                "src_inst_uuid": "63e4a531-b6bb-43cc-9eae-8eb8a09f795e",
                "dst_inst_uuid": "73e4a531-b6bb-43cc-9eae-8eb8a09f795e",
            },
        )
    ]
    assert graph.edge_removals == [([188], ["src_inst_id", "dst_inst_id"])]


def test_clean_graph_dry_run_builds_uuid_map_without_writes(monkeypatch):
    entities = [{"_id": 1}, {"_id": 2}]
    graph = _Graph(
        entities,
        [
            {
                "edge": {"_id": 9, "model_asst_id": "a", "src_inst_id": 1, "dst_inst_id": 2},
                "src": entities[0],
                "dst": entities[1],
            }
        ],
    )
    monkeypatch.setattr(
        "apps.cmdb.management.commands.migrate_cmdb_instance_uuid_refs.GraphClient",
        lambda: graph,
    )
    command = Command()
    command._graph_uuid_by_id = {}

    command._clean_graph(batch_size=100, dry_run=True, stats=_stats())

    assert graph.node_updates == []
    assert graph.edge_sets == []
    assert graph.edge_removals == []
    assert len(command._graph_uuid_by_id) == 2


def test_clean_graph_rejects_duplicate_uuid(monkeypatch):
    duplicate_uuid = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
    graph = _Graph(
        [{"_id": 1, "inst_uuid": duplicate_uuid}, {"_id": 2, "inst_uuid": duplicate_uuid}],
        [],
    )
    monkeypatch.setattr(
        "apps.cmdb.management.commands.migrate_cmdb_instance_uuid_refs.GraphClient",
        lambda: graph,
    )
    command = Command()
    command._graph_uuid_by_id = {}

    with pytest.raises(CommandError, match="inst_uuid 重复"):
        command._clean_graph(batch_size=100, dry_run=True, stats=_stats())


def test_rewrite_node_mgmt_sync_detail_adds_uuid_keeps_graph_id():
    inst_uuid = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
    detail = {
        "add": {"data": [{"_id": 7, "inst_name": "host-a"}]},
        "update": {"data": [{"_id": 999, "inst_name": "deleted-host"}]},
    }

    rewritten, changed = Command._rewrite_node_mgmt_sync_detail(detail, {7: inst_uuid})

    assert changed is True
    assert rewritten["add"]["data"][0]["_id"] == 7
    assert rewritten["add"]["data"][0]["inst_uuid"] == inst_uuid
    assert "inst_uuid" not in rewritten["update"]["data"][0]


@pytest.mark.django_db
def test_clean_config_versions_fills_uuid_from_graph_map():
    from apps.cmdb.models.config_file_version import ConfigFileVersion

    inst_uuid = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
    row = ConfigFileVersion.objects.create(
        instance_id="7",
        model_id="host",
        version="100",
        file_path="/etc/app.conf",
        file_name="app.conf",
        status="success",
    )
    command = Command()
    command._graph_uuid_by_id = {7: inst_uuid}
    command._dry_run = False
    command._stage_cursor = lambda stage: (0, False)
    command._save_stage = lambda *args, **kwargs: None
    stats = {"config_updated": 0, "config_orphan_skipped": 0}

    command._clean_config_versions(batch_size=50, dry_run=False, stats=stats)

    row.refresh_from_db()
    assert str(row.instance_uuid) == inst_uuid
    assert stats["config_updated"] == 1
    assert stats["config_orphan_skipped"] == 0
