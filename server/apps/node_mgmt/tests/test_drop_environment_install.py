"""已执行过环境安装迁移的库，清理后不再留下表、令牌和迁移记录。"""

from importlib import import_module

import pytest
from django.apps import apps
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder

from apps.system_mgmt.models import SystemAPIToken

cleanup = import_module("apps.node_mgmt.migrations.0050_drop_environment_install")

pytestmark = pytest.mark.django_db(transaction=True)


def _create_leftover_tables():
    with connection.schema_editor() as schema_editor:
        schema_editor.execute("CREATE TABLE node_mgmt_environmentinstallgrant (id char(32) NOT NULL PRIMARY KEY)")
        schema_editor.execute(
            "CREATE TABLE node_mgmt_environmentinstallattempt ("
            "id char(32) NOT NULL PRIMARY KEY, "
            "grant_id char(32) NOT NULL REFERENCES node_mgmt_environmentinstallgrant (id)"
            ")"
        )


def test_cleanup_removes_applied_environment_install_state():
    with connection.schema_editor() as schema_editor:
        cleanup.drop_environment_install_tables(apps, schema_editor)
    _create_leftover_tables()
    SystemAPIToken.objects.create(
        system_id=cleanup.TOKEN_SYSTEM_ID,
        name="environment-grant",
        secret_hash=SystemAPIToken.hash_secret("bksys_" + "ab" * 32),
    )
    kept = SystemAPIToken.objects.create(
        system_id="kept-system",
        name="kept",
        secret_hash=SystemAPIToken.hash_secret("bksys_" + "cd" * 32),
    )
    MigrationRecorder.Migration.objects.create(app="node_mgmt", name=cleanup.REMOVED_MIGRATION)

    with connection.schema_editor() as schema_editor:
        cleanup.drop_environment_install_tables(apps, schema_editor)
        cleanup.drop_environment_install_tables(apps, schema_editor)
    cleanup.purge_environment_install_records(apps, None)

    existing = set(connection.introspection.table_names())
    assert set(cleanup.ENVIRONMENT_INSTALL_TABLES).isdisjoint(existing)
    assert not SystemAPIToken.objects.filter(system_id=cleanup.TOKEN_SYSTEM_ID).exists()
    assert SystemAPIToken.objects.filter(pk=kept.pk).exists()
    assert not MigrationRecorder.Migration.objects.filter(app="node_mgmt", name=cleanup.REMOVED_MIGRATION).exists()
