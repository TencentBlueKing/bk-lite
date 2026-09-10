from contextlib import nullcontext

import pytest
from django.core.management.base import CommandError

from apps.cmdb.management.commands.migrate_oa_cmdb_instance_uuid_refs import Command


class _RenderSnapshotRow:
    pk = 1
    view_sets = [{"valueConfig": {"networkStatusTopology": {"instId": 10001}}}]
    filters = []
    other = {}


class _ImmutableRenderSnapshotManager:
    def __init__(self):
        self.row = _RenderSnapshotRow()
        self.lower_bound = 0
        self.migrated_fields = None

    def filter(self, **kwargs):
        if "pk__gt" in kwargs:
            self.lower_bound = kwargs["pk__gt"]
        return self

    def order_by(self, *_args):
        return self

    def __getitem__(self, _key):
        return [self.row] if self.lower_bound < self.row.pk else []

    def bulk_update(self, _rows, _fields):
        raise AssertionError("普通 bulk_update 不得修改不可变 Render Snapshot")


class _RenderSnapshotModel:
    objects = _ImmutableRenderSnapshotManager()


def test_clean_operation_analysis_refs_uses_controlled_render_snapshot_migration_writer(monkeypatch):
    inst_uuid = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
    command = Command()
    command._graph_uuid_by_id = {10001: inst_uuid}
    monkeypatch.setattr(
        command,
        "_bulk_update_render_snapshots",
        lambda _model, rows, fields: setattr(
            _RenderSnapshotModel.objects,
            "migrated_fields",
            (rows, fields),
        ),
    )
    monkeypatch.setattr(command, "_model_table_exists", lambda _model: True)
    monkeypatch.setattr(command, "_stage_cursor", lambda _stage: (0, False))
    monkeypatch.setattr(command, "_save_stage", lambda *_args, **_kwargs: None)

    def get_model(_app_label, model_name):
        if model_name == "DashboardReportRenderSnapshot":
            return _RenderSnapshotModel
        raise LookupError

    monkeypatch.setattr(
        "apps.cmdb.management.commands.migrate_oa_cmdb_instance_uuid_refs.django_apps.get_model",
        get_model,
    )
    stats = {
        "operation_analysis_record_updated": 0,
        "operation_analysis_orphan_removed": 0,
    }

    command._clean_operation_analysis_refs(batch_size=10, dry_run=False, stats=stats)

    assert _RenderSnapshotModel.objects.row.view_sets[0]["valueConfig"]["networkStatusTopology"] == {
        "instUuid": inst_uuid,
    }
    assert _RenderSnapshotModel.objects.migrated_fields == (
        [_RenderSnapshotModel.objects.row],
        ["view_sets", "filters", "other"],
    )


def test_render_snapshot_migration_writer_is_command_scoped_and_field_limited(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "apps.cmdb.management.commands.migrate_oa_cmdb_instance_uuid_refs.transaction.atomic",
        nullcontext,
    )
    monkeypatch.setattr(
        "apps.cmdb.management.commands.migrate_oa_cmdb_instance_uuid_refs.models.QuerySet.update",
        lambda queryset, **values: calls.append((queryset, values)) or 1,
    )

    updated = Command._bulk_update_render_snapshots(
        _RenderSnapshotModel,
        [_RenderSnapshotModel.objects.row],
        ["view_sets", "filters", "other"],
    )

    assert updated == 1
    assert calls == [
        (
            _RenderSnapshotModel.objects,
            {
                "view_sets": _RenderSnapshotModel.objects.row.view_sets,
                "filters": [],
                "other": {},
            },
        )
    ]
    with pytest.raises(CommandError, match="只允许修改"):
        Command._bulk_update_render_snapshots(
            _RenderSnapshotModel,
            [_RenderSnapshotModel.objects.row],
            ["dashboard_name"],
        )


def test_oa_uuid_migration_excludes_weops_network_topology():
    assert "NetworkTopology" not in Command.OA_UUID_MODEL_FIELDS


def test_rewrite_renames_bk_inst_id_and_inst_id_aliases():
    inst_uuid = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
    stats = {"operation_analysis_orphan_removed": 0}
    payload = {
        "nodes": [
            {"id": "n1", "bk_obj_id": "bk_switch", "bk_inst_id": 10001},
            {"id": "n2", "data": {"instId": 10002}},
        ],
        "links": [
            {
                "id": "l1",
                "source_node_id": "n1",
                "target_node_id": "n2",
                "port_pairs": [
                    {
                        "source_interface": {"bk_obj_id": "bk_interface", "bk_inst_id": 90001},
                        "target_interface": {"bk_obj_id": "bk_interface", "bk_inst_id": 90002},
                    }
                ],
            }
        ],
    }

    rewritten, changed, orphan = Command()._rewrite_operation_analysis_value(
        payload,
        {
            10001: inst_uuid,
            10002: "c28e467a-501d-426f-a3c3-6e560c7b33cb",
            90001: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            90002: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        },
        stats,
    )

    assert changed is True
    assert orphan is False
    assert rewritten["nodes"][0]["bk_inst_uuid"] == inst_uuid
    assert "bk_inst_id" not in rewritten["nodes"][0]
    assert rewritten["nodes"][1]["data"]["instUuid"] == "c28e467a-501d-426f-a3c3-6e560c7b33cb"
    assert "instId" not in rewritten["nodes"][1]["data"]
    assert rewritten["links"][0]["port_pairs"][0]["source_interface"]["bk_inst_uuid"]


def test_rewrite_drops_orphan_identity_nodes():
    stats = {"operation_analysis_orphan_removed": 0}
    payload = {
        "nodes": [{"id": "n1", "bk_inst_id": 999}],
        "links": [{"id": "l1", "source_node_id": "n1", "target_node_id": "missing"}],
    }

    rewritten, changed, orphan = Command()._rewrite_operation_analysis_value(payload, {}, stats)

    assert changed is True
    assert orphan is False
    assert rewritten["nodes"] == []
    assert rewritten["links"] == []
    assert stats["operation_analysis_orphan_removed"] >= 1
