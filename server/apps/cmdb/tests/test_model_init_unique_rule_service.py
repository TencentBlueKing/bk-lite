import json
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command

from apps.cmdb.constants.constants import INSTANCE, MODEL
from apps.cmdb.services.model import ModelManage
from apps.cmdb.services.unique_rule import UniqueRuleConflict
from apps.core.exceptions.base_app_exception import BaseAppException

pytestmark = pytest.mark.unit


def test_model_init_enables_existing_unique_rule_conflict_tolerance():
    with (
        patch("apps.cmdb.management.commands.model_init.ModelMigrate") as mock_migrator_cls,
        patch("apps.cmdb.management.commands.model_init.ModelManage._apply_model_config_post_import_extras") as mock_apply_extras,
    ):
        mock_migrator = MagicMock()
        mock_migrator.model_config = {"attr-host": []}
        mock_migrator.main.return_value = {"ok": True}
        mock_migrator_cls.return_value = mock_migrator

        call_command("model_init")

    mock_migrator_cls.assert_called_once_with(sync_app_topo_layer=False)
    mock_apply_extras.assert_called_once_with(
        mock_migrator.model_config,
        keep_existing_unique_rules_on_conflict=True,
    )


def test_model_init_passes_sync_app_topo_layer_flag():
    with (
        patch("apps.cmdb.management.commands.model_init.ModelMigrate") as mock_migrator_cls,
        patch("apps.cmdb.management.commands.model_init.ModelManage._apply_model_config_post_import_extras") as mock_apply_extras,
    ):
        mock_migrator = MagicMock()
        mock_migrator.model_config = {"attr-host": []}
        mock_migrator.main.return_value = {"ok": True}
        mock_migrator_cls.return_value = mock_migrator

        call_command("model_init", "--sync-app-topo-layer")

    mock_migrator_cls.assert_called_once_with(sync_app_topo_layer=True)
    mock_apply_extras.assert_called_once_with(
        mock_migrator.model_config,
        keep_existing_unique_rules_on_conflict=True,
    )


def _host_model(*, unique_rules):
    return {
        "_id": 10,
        "model_id": "host",
        "attrs": json.dumps(
            [
                {"attr_id": "ip_addr", "attr_name": "内网IP", "attr_type": "str", "is_required": True},
                {"attr_id": "cloud", "attr_name": "云区域", "attr_type": "str", "is_required": True},
            ]
        ),
        "unique_rules": json.dumps(unique_rules),
    }


def _host_rows():
    return [
        {"attr_id": "ip_addr", "unique_rule_order": 1},
        {"attr_id": "cloud", "unique_rule_order": 1},
    ]


class _RuleGraph:
    def __init__(self, model):
        self.model = model
        self.labels = []
        self.writes = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def query_entity(self, label, _params, **_kwargs):
        self.labels.append(label)
        if label == MODEL:
            return [self.model], 1
        return [{"_id": 101, "ip_addr": "10.0.0.1", "cloud": "a"}, {"_id": 102, "ip_addr": "10.0.0.1", "cloud": "a"}], 2

    def set_entity_properties(self, *args, **_kwargs):
        self.writes.append(args)


def _apply_host_rules(graph, *, keep_existing):
    with (
        patch("apps.cmdb.services.model.GraphClient", return_value=graph),
        patch.object(ModelManage, "_import_auto_relation_rule_sets_from_asso_sheets") as mock_import_associations,
        patch("apps.cmdb.services.module_ingest.SUPPORTED_INGEST_MODELS", set()),
        patch("apps.cmdb.services.host_zombie_whitelist.ensure_host_zombie_whitelist_attr", return_value=True),
    ):
        ModelManage._apply_model_config_post_import_extras(
            {"attr-host": _host_rows(), "asso-host": []},
            keep_existing_unique_rules_on_conflict=keep_existing,
        )
    return mock_import_associations


def test_startup_matching_unique_rules_do_not_read_instances_or_write():
    stored = [{"rule_id": "keep-me", "order": 1, "field_ids": ["ip_addr", "cloud"]}]
    graph = _RuleGraph(_host_model(unique_rules=stored))

    _apply_host_rules(graph, keep_existing=True)

    assert graph.labels == [MODEL]
    assert graph.writes == []


@pytest.mark.django_db
def test_startup_changed_unique_rules_are_deferred_without_reading_instances(caplog):
    import logging

    from apps.cmdb.models.repair_state import CmdbRepairState

    graph = _RuleGraph(_host_model(unique_rules=[]))
    with caplog.at_level(logging.DEBUG, logger="cmdb"):
        associations = _apply_host_rules(graph, keep_existing=True)

    associations.assert_called_once()
    assert INSTANCE not in graph.labels
    assert graph.writes == []
    row = CmdbRepairState.objects.get(stage="unique_rule:host")
    assert row.completed is False
    assert json.loads(row.fingerprint) == [["ip_addr", "cloud"]]
    records = [record for record in caplog.records if record.msg == "event=unique_rule_startup_deferred model_id=%s"]
    assert len(records) == 1
    assert records[0].args == ("host",)
    assert records[0].getMessage() == "event=unique_rule_startup_deferred model_id=host"
    assert "10.0.0.1" not in caplog.text


def test_manual_import_still_rejects_conflicting_unique_rules():
    graph = _RuleGraph(_host_model(unique_rules=[]))
    conflict = UniqueRuleConflict(
        rule_id="rule-1",
        rule_order=1,
        field_ids=["ip_addr", "cloud"],
        field_names=["内网IP", "云区域"],
        field_values={"ip_addr": "10.0.0.1", "cloud": "a"},
        exist_instance_ids=[101, 102],
        exist_instance_names=["host-a", "host-b"],
        message="规则冲突",
    )
    with (
        patch("apps.cmdb.services.model.GraphClient", return_value=graph),
        patch(
            "apps.cmdb.services.model.validate_unique_rules_against_existing_instances",
            return_value=[conflict],
        ),
        patch.object(ModelManage, "_import_auto_relation_rule_sets_from_asso_sheets"),
        patch("apps.cmdb.services.module_ingest.SUPPORTED_INGEST_MODELS", set()),
        patch("apps.cmdb.services.host_zombie_whitelist.ensure_host_zombie_whitelist_attr", return_value=True),
        pytest.raises(BaseAppException, match="规则冲突"),
    ):
        ModelManage._apply_model_config_post_import_extras({"attr-host": _host_rows()})

    assert INSTANCE in graph.labels
    assert graph.writes == []


def test_manual_import_keeps_strict_unique_rule_conflict_policy():
    fake_file = MagicMock()
    fake_model_config = {"attr-host": []}

    with (
        patch("apps.cmdb.model_migrate.migrete_service.ModelMigrate") as mock_migrator_cls,
        patch.object(ModelManage, "_apply_model_config_post_import_extras") as mock_apply_extras,
    ):
        mock_migrator = MagicMock()
        mock_migrator.model_config = fake_model_config
        mock_migrator.main.return_value = {"ok": True}
        mock_migrator_cls.return_value = mock_migrator

        ModelManage.import_model_config(fake_file)

    mock_apply_extras.assert_called_once_with(fake_model_config)
