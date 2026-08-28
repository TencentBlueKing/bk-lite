from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command

from apps.cmdb.services.model import ModelManage
from apps.cmdb.services.unique_rule import ModelUniqueRule, UniqueRuleConflict

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


def test_startup_unique_rule_conflict_keeps_existing_rules_and_continues(caplog):
    conflict = UniqueRuleConflict(
        rule_id="rule-1",
        rule_order=1,
        field_ids=["ip_addr", "cloud"],
        field_names=["内网IP", "云区域"],
        field_values={"ip_addr": "172.168.23.12", "cloud": "1"},
        exist_instance_ids=[101, 102],
        exist_instance_names=["host-a", "host-b"],
        message="规则 1【内网IP + 云区域】与现有实例冲突：内网IP=172.168.23.12，云区域=1",
    )
    graph = MagicMock()
    graph.query_entity.return_value = ([{"_id": 101}, {"_id": 102}], 2)
    graph_context = MagicMock()
    graph_context.__enter__.return_value = graph

    rules = [ModelUniqueRule(rule_id="rule-1", order=1, field_ids=["ip_addr", "cloud"])]
    with (
        patch("apps.cmdb.services.model.GraphClient", return_value=graph_context),
        patch.object(
            ModelManage,
            "search_model_info",
            return_value={"_id": 10},
        ),
        patch(
            "apps.cmdb.services.model.build_unique_rules_from_attr_rows",
            return_value=rules,
        ),
        patch(
            "apps.cmdb.services.model.validate_unique_rules_against_existing_instances",
            return_value=[conflict],
        ),
        patch.object(
            ModelManage,
            "_import_auto_relation_rule_sets_from_asso_sheets",
        ) as mock_import_associations,
        patch(
            "apps.cmdb.services.module_ingest.SUPPORTED_INGEST_MODELS",
            set(),
        ),
    ):
        ModelManage._apply_model_config_post_import_extras(
            {"attr-host": [{"attr_id": "ip_addr"}], "asso-host": []},
            keep_existing_unique_rules_on_conflict=True,
        )

    graph.set_entity_properties.assert_not_called()
    mock_import_associations.assert_called_once()
    assert "保留原唯一规则并继续初始化" in caplog.text
    assert "model_id=host" in caplog.text
    assert conflict.message in caplog.text


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
