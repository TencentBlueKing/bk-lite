from django.db import migrations

from apps.core.logger import cmdb_logger as logger


def drop_ip_host_table(apps, schema_editor):
    try:
        from apps.cmdb.services.ipam_model_cleanup import drop_ip_host_table_attr

        drop_ip_host_table_attr()
    except Exception:
        logger.exception("[IPAM] 迁移删除 IP 主机表格字段失败，将在模型初始化时重试")


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0047_enable_nodemgmtsync_auto_sync_default"),
    ]

    operations = [
        migrations.RunPython(drop_ip_host_table, migrations.RunPython.noop),
    ]
