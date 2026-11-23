"""去掉已执行过的环境安装表、授权令牌和旧迁移记录。"""

from django.db import migrations
from django.db.migrations.recorder import MigrationRecorder

REMOVED_MIGRATION = "0050_environmentinstallgrant_environmentinstallattempt_and_more"
TOKEN_SYSTEM_ID = "node-environment-install"
ENVIRONMENT_INSTALL_TABLES = (
    "node_mgmt_environmentinstallattempt",
    "node_mgmt_environmentinstallgrant",
)


def drop_environment_install_tables(apps, schema_editor):
    del apps
    existing = set(schema_editor.connection.introspection.table_names())
    for name in ENVIRONMENT_INSTALL_TABLES:
        if name not in existing:
            continue
        schema_editor.execute("DROP TABLE %s" % schema_editor.quote_name(name))


def purge_environment_install_records(apps, schema_editor):
    del schema_editor
    token = apps.get_model("system_mgmt", "SystemAPIToken")
    token.objects.filter(system_id=TOKEN_SYSTEM_ID).delete()
    MigrationRecorder.Migration.objects.filter(app="node_mgmt", name=REMOVED_MIGRATION).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("node_mgmt", "0049_collector_default_backfill"),
        ("system_mgmt", "0057_channel_account_association"),
    ]

    operations = [
        migrations.RunPython(drop_environment_install_tables, migrations.RunPython.noop),
        migrations.RunPython(purge_environment_install_records, migrations.RunPython.noop),
    ]
