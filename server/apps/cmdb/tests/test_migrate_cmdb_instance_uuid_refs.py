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


def test_rewrite_json_uuids_fills_inst_uuid_and_keeps_graph_id():
    inst_uuid = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
    payload = {
        "add": [{"_id": 7, "inst_name": "host-a"}],
        "association": [{"src_inst_id": 7, "dst_inst_id": 8}],
        "subnet_ids": [7],
    }

    rewritten, changed = Command._rewrite_json_uuids(payload, {7: inst_uuid})

    assert changed is True
    assert rewritten["add"][0]["_id"] == 7
    assert rewritten["add"][0]["inst_uuid"] == inst_uuid
    assert rewritten["association"][0]["src_inst_uuid"] == inst_uuid
    assert "dst_inst_uuid" not in rewritten["association"][0]
    assert rewritten["subnet_uuids"] == [inst_uuid]
    assert rewritten["subnet_ids"] == [7]


def test_rewrite_json_uuids_skips_unmapped_ids():
    payload = {"_id": 999, "inst_name": "gone"}
    rewritten, changed = Command._rewrite_json_uuids(payload, {7: "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"})
    assert changed is False
    assert "inst_uuid" not in rewritten
    assert rewritten["_id"] == 999


def test_rewrite_json_uuids_skips_vendor_instance_id():
    inst_uuid = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
    payload = {"instance_id": 7, "name": "i-xxx"}
    rewritten, changed = Command._rewrite_json_uuids(payload, {7: inst_uuid})
    assert changed is False
    assert "instance_uuid" not in rewritten
    assert rewritten["instance_id"] == 7


def test_rewrite_json_uuids_fills_operation_instance_id_when_allowed():
    inst_uuid = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
    rewritten, changed = Command._rewrite_json_uuids({"instance_id": 7}, {7: inst_uuid}, allow_bare_instance_id=True)
    assert changed is True
    assert rewritten["instance_id"] == 7
    assert rewritten["instance_uuid"] == inst_uuid


def test_rewrite_subscription_snapshot_dual_writes_uuid_keys():
    host_uuid = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
    switch_uuid = "73e4a531-b6bb-43cc-9eae-8eb8a09f795e"
    snapshot = {
        "instances": [1],
        "relations": {"1": {"switch": [10]}},
    }

    rewritten, changed = Command._rewrite_subscription_snapshot(snapshot, {1: host_uuid, 10: switch_uuid})

    assert changed is True
    assert rewritten["instances"] == [1]
    assert rewritten["instance_uuids"] == [host_uuid]
    assert rewritten["relations"] == {"1": {"switch": [10]}}
    assert rewritten["relations_by_uuid"] == {host_uuid: {"switch": [switch_uuid]}}


@pytest.mark.django_db
def test_clean_subscription_snapshots_fills_uuid_and_keeps_digits():
    from apps.cmdb.models.subscription_rule import SubscriptionRule

    host_uuid = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
    rule = SubscriptionRule.objects.create(
        name="snap-uuid",
        organization=1,
        model_id="host",
        filter_type="instances",
        instance_filter={"instance_ids": [1]},
        trigger_types=[],
        trigger_config={},
        recipients={},
        channel_ids=[],
        is_enabled=True,
        snapshot_data={"instances": [1], "relations": {"1": {"switch": [10]}}},
    )
    command = Command()
    command._graph_uuid_by_id = {1: host_uuid}
    command._dry_run = False
    command._stage_cursor = lambda stage: (0, False)
    command._save_stage = lambda *args, **kwargs: None
    stats = {"subscription_snapshot_updated": 0}

    command._clean_subscription_snapshots(batch_size=50, dry_run=False, stats=stats)

    rule.refresh_from_db()
    assert rule.snapshot_data["instances"] == [1]
    assert rule.snapshot_data["instance_uuids"] == [host_uuid]
    assert rule.snapshot_data["relations"]["1"]["switch"] == [10]
    assert stats["subscription_snapshot_updated"] == 1


@pytest.mark.django_db
def test_clean_collect_instances_fills_list_and_subnet_uuids():
    from apps.cmdb.constants.constants import CollectPluginTypes
    from apps.cmdb.models.collect_model import CollectModels

    inst_uuid = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
    task = CollectModels.objects.create(
        name="collect-uuid",
        task_type=CollectPluginTypes.HOST,
        model_id="host",
        cycle_value_type="cycle",
        team=[1],
        instances=[{"_id": 7, "inst_name": "host-a", "model_id": "host"}],
        params={"subnet_ids": [7]},
    )
    command = Command()
    command._graph_uuid_by_id = {7: inst_uuid}
    command._dry_run = False
    command._stage_cursor = lambda stage: (0, False)
    command._save_stage = lambda *args, **kwargs: None
    stats = {"collect_instance_updated": 0, "collect_reference_unmapped": 0}

    command._clean_collect_instances(batch_size=50, dry_run=False, stats=stats)

    task.refresh_from_db()
    assert task.instances[0]["_id"] == 7
    assert task.instances[0]["inst_uuid"] == inst_uuid
    assert task.params["subnet_ids"] == [7]
    assert task.params["subnet_uuids"] == [inst_uuid]
    assert stats["collect_instance_updated"] == 1
    assert stats["collect_reference_unmapped"] == 0


@pytest.mark.django_db
def test_clean_collect_instances_reports_unmapped_active_reference():
    from apps.cmdb.constants.constants import CollectPluginTypes
    from apps.cmdb.models.collect_model import CollectModels

    CollectModels.objects.create(
        name="collect-unmapped",
        task_type=CollectPluginTypes.HOST,
        model_id="host",
        cycle_value_type="cycle",
        team=[1],
        instances=[{"_id": 999, "inst_name": "deleted-host"}],
    )
    command = Command()
    command._graph_uuid_by_id = {}
    command._dry_run = True
    command._stage_cursor = lambda stage: (0, False)
    command._save_stage = lambda *args, **kwargs: None
    stats = {"collect_instance_updated": 0, "collect_reference_unmapped": 0}

    command._clean_collect_instances(batch_size=50, dry_run=True, stats=stats)

    assert stats["collect_instance_updated"] == 0
    assert stats["collect_reference_unmapped"] == 1


@pytest.mark.django_db
def test_clean_followed_assets_replaces_numeric_id_and_removes_alias():
    from apps.cmdb.models.user_personal_config import UserPersonalConfig

    inst_uuid = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
    config = UserPersonalConfig.objects.create(
        username="alice",
        domain="local",
        config_key="cmdb_followed_assets",
        config_value={"items": [{"model_id": "host", "inst_id": 7, "followed_at": "2026-01-01T00:00:00Z"}]},
    )
    command = Command()
    command._graph_uuid_by_id = {7: inst_uuid}
    command._dry_run = False
    command._stage_cursor = lambda stage: (0, False)
    command._save_stage = lambda *args, **kwargs: None
    stats = {"followed_asset_config_updated": 0, "followed_asset_unmapped": 0}

    command._clean_followed_assets(batch_size=50, dry_run=False, stats=stats)

    config.refresh_from_db()
    assert config.config_value["items"][0]["inst_uuid"] == inst_uuid
    assert "inst_id" not in config.config_value["items"][0]
    assert stats == {"followed_asset_config_updated": 1, "followed_asset_unmapped": 0}


@pytest.mark.django_db
def test_clean_collect_result_snapshots_adds_uuid_to_format_data():
    from apps.cmdb.constants.constants import CollectPluginTypes
    from apps.cmdb.models.collect_model import CollectModels

    inst_uuid = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
    task = CollectModels.objects.create(
        name="collect-result-uuid",
        task_type=CollectPluginTypes.HOST,
        model_id="host",
        cycle_value_type="cycle",
        team=[1],
        format_data={"add": [{"_id": 7, "inst_name": "host-a"}]},
    )
    command = Command()
    command._graph_uuid_by_id = {7: inst_uuid}
    command._dry_run = False
    command._stage_cursor = lambda stage: (0, False)
    command._save_stage = lambda *args, **kwargs: None
    stats = {"collect_result_snapshot_updated": 0}

    command._clean_collect_result_snapshots(batch_size=50, dry_run=False, stats=stats)

    task.refresh_from_db()
    assert task.format_data["add"][0]["inst_uuid"] == inst_uuid
    assert task.format_data["add"][0]["_id"] == 7


@pytest.mark.django_db
def test_clean_collect_result_snapshots_rescans_after_stage_completed():
    from apps.cmdb.constants.constants import CollectPluginTypes
    from apps.cmdb.models.collect_model import CollectModels
    from apps.cmdb.models.uuid_migration_state import CmdbUuidMigrationState

    inst_uuid = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
    task = CollectModels.objects.create(
        name="collect-result-uuid-reentry",
        task_type=CollectPluginTypes.HOST,
        model_id="host",
        cycle_value_type="cycle",
        team=[1],
        format_data={"add": [{"_id": 7, "inst_name": "host-a", "inst_uuid": inst_uuid}]},
    )
    CmdbUuidMigrationState.objects.update_or_create(
        stage="collect_result_snapshots",
        defaults={"cursor": str(task.id), "completed": True},
    )
    task.format_data = {"add": [{"_id": 7, "inst_name": "host-a"}]}
    task.save(update_fields=["format_data"])

    command = Command()
    command._graph_uuid_by_id = {7: inst_uuid}
    command._dry_run = False
    stats = {"collect_result_snapshot_updated": 0}

    command._clean_collect_result_snapshots(batch_size=50, dry_run=False, stats=stats)

    task.refresh_from_db()
    assert task.format_data["add"][0]["inst_uuid"] == inst_uuid
    assert stats["collect_result_snapshot_updated"] == 1
    assert command._leftover_snapshot_ids == [task.id]


@pytest.mark.django_db
def test_verify_reports_leftover_snapshot_ids(monkeypatch):
    from apps.cmdb.constants.constants import CollectPluginTypes
    from apps.cmdb.models.collect_model import CollectModels

    inst_uuid = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
    task = CollectModels.objects.create(
        name="collect-result-uuid-verify",
        task_type=CollectPluginTypes.HOST,
        model_id="host",
        cycle_value_type="cycle",
        team=[1],
        format_data={"add": [{"_id": 7, "inst_name": "host-a"}]},
    )
    command = Command()

    def _noop(*_args, **_kwargs):
        return None

    for name in dir(Command):
        if name.startswith("_clean_") and name != "_clean_collect_result_snapshots":
            monkeypatch.setattr(command, name, _noop)
    monkeypatch.setattr(
        "apps.cmdb.management.commands.migrate_cmdb_instance_uuid_refs.InstanceManage.query_entity_by_ids",
        staticmethod(lambda ids: [{"_id": 7, "inst_uuid": inst_uuid}] if 7 in ids else []),
    )

    with pytest.raises(CommandError, match=rf"leftover_ids=\[{task.id}\]"):
        command.handle(batch_size=50, verify=True, apply=False, dry_run=False)


@pytest.mark.django_db
def test_clean_operation_snapshots_and_skip_success_outbox():
    from apps.cmdb.models.operation import CmdbOperation, CmdbOperationOutbox, CmdbOperationOutboxStatus, CmdbOperationStatus

    inst_uuid = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
    pending = CmdbOperation.objects.create(
        operator="alice",
        idempotency_key="op-pending",
        request_hash="a" * 64,
        action="instance.create",
        target={"model_id": "host", "instance_id": 7},
        request_snapshot={"instance_id": 7},
        result_snapshot={"_id": 7, "model_id": "host"},
        status=CmdbOperationStatus.GRAPH_COMMITTED,
    )
    success_outbox = CmdbOperationOutbox.objects.create(
        operation=pending,
        event_type="change_record",
        payload={"_id": 7},
        status=CmdbOperationOutboxStatus.SUCCESS,
    )
    pending_outbox = CmdbOperationOutbox.objects.create(
        operation=pending,
        event_type="auto_relation",
        payload={"_id": 7},
        status=CmdbOperationOutboxStatus.PENDING,
    )
    command = Command()
    command._graph_uuid_by_id = {7: inst_uuid}
    command._dry_run = False
    command._stage_cursor = lambda stage: (0, False)
    command._save_stage = lambda *args, **kwargs: None
    stats = {"operation_snapshot_updated": 0, "operation_outbox_updated": 0}

    command._clean_operation_snapshots(batch_size=50, dry_run=False, stats=stats)
    command._clean_operation_outbox(batch_size=50, dry_run=False, stats=stats)

    pending.refresh_from_db()
    success_outbox.refresh_from_db()
    pending_outbox.refresh_from_db()
    assert pending.result_snapshot["inst_uuid"] == inst_uuid
    assert pending.request_snapshot["instance_uuid"] == inst_uuid
    assert "inst_uuid" not in success_outbox.payload
    assert pending_outbox.payload["inst_uuid"] == inst_uuid
    assert stats["operation_outbox_updated"] == 1


def test_missing_model_marks_stage_completed(monkeypatch):
    saved = []
    command = Command()
    command._dry_run = False
    command._save_stage = lambda stage, cursor, completed=False: saved.append((stage, completed))
    monkeypatch.setattr(
        "apps.cmdb.management.commands.migrate_cmdb_instance_uuid_refs.django_apps.get_model",
        lambda *args, **kwargs: (_ for _ in ()).throw(LookupError("missing")),
    )
    command._clean_node_mgmt_sync_details(50, False, {"node_mgmt_sync_detail_updated": 0})
    command._clean_operation_targets(50, False, {"operation_target_updated": 0})
    command._clean_monitor_cmdb_ids(50, False, {"monitor_cmdb_id_updated": 0, "monitor_cmdb_id_unmapped": 0})
    command._clean_node_cmdb_ids(50, False, {"node_cmdb_id_updated": 0, "node_cmdb_id_unmapped": 0})
    assert ("node_mgmt_sync_details", True) in saved
    assert ("operation_targets", True) in saved
    assert ("monitor_cmdb_ids", True) in saved
    assert ("node_cmdb_ids", True) in saved


@pytest.mark.django_db
def test_clean_monitor_and_node_cmdb_ids_rewrites_digits():
    from apps.monitor.models import MonitorInstance, MonitorObject
    from apps.node_mgmt.models.cloud_region import CloudRegion
    from apps.node_mgmt.models.sidecar import Node

    inst_uuid = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
    host_object = MonitorObject.objects.create(name="Host", display_name="主机", level="base")
    monitor = MonitorInstance.objects.create(
        id="mon-uuid-clean",
        name="m1",
        monitor_object=host_object,
        cmdb_id="7",
    )
    region = CloudRegion.objects.create(name="uuid-clean-region")
    node = Node.objects.create(
        id="node-uuid-clean",
        name="n1",
        ip="10.0.0.7",
        operating_system="linux",
        collector_configuration_directory="/tmp",
        cloud_region=region,
        cmdb_id="7",
    )

    command = Command()
    command._graph_uuid_by_id = {7: inst_uuid}
    command._dry_run = False
    command._stage_cursor_str = lambda stage: ("", False)
    command._save_stage = lambda *args, **kwargs: None
    stats = {
        "monitor_cmdb_id_updated": 0,
        "monitor_cmdb_id_unmapped": 0,
        "node_cmdb_id_updated": 0,
        "node_cmdb_id_unmapped": 0,
    }
    command._clean_monitor_cmdb_ids(50, False, stats)
    command._clean_node_cmdb_ids(50, False, stats)

    monitor.refresh_from_db()
    node.refresh_from_db()
    assert monitor.cmdb_id == inst_uuid
    assert node.cmdb_id == inst_uuid
    assert stats["monitor_cmdb_id_updated"] == 1
    assert stats["node_cmdb_id_updated"] == 1
