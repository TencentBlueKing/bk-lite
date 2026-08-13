import importlib

import pytest
from django.apps import apps
from django.db import connection

pytestmark = pytest.mark.django_db


def test_0045_transition_adds_nullable_uuid_columns_without_dropping_instance_id():
    migration = importlib.import_module("apps.cmdb.migrations.0045_instance_uuid_transition")
    assert migration.Migration.dependencies == [("cmdb", "0044_alter_nodemgmtsyncconfig_auto_sync_enabled_default")]

    change_record = apps.get_model("cmdb", "ChangeRecord")
    config_version = apps.get_model("cmdb", "ConfigFileVersion")
    state = apps.get_model("cmdb", "CmdbUuidMigrationState")

    change_fields = {field.name for field in change_record._meta.get_fields()}
    config_fields = {field.name for field in config_version._meta.get_fields()}

    assert "inst_uuid" in change_fields
    assert "inst_id" in change_fields
    assert change_record._meta.get_field("inst_id").null is True
    assert change_record._meta.get_field("inst_uuid").null is True

    assert "instance_id" in config_fields
    assert "instance_uuid" in config_fields
    assert config_version._meta.get_field("instance_uuid").null is True

    assert state._meta.db_table in connection.introspection.table_names()

    # 唯一约束仍基于旧列；本迁移不得删列
    constraint_names = {constraint.name for constraint in config_version._meta.constraints}
    assert "uniq_cfg_ver_task_inst_version" in constraint_names
