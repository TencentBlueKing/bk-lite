"""将监控对象分类「主机资源」恢复为「操作系统」。

与 0044_rename_monitor_object_type_os_to_host_resource 对冲：
视图层优先从 i18n 读取 type 显示名，i18n 缺失时回退到 MonitorObjectType.name；
同步更新 DB 兜底字段，避免 admin 等入口仍展示旧值。
"""
from django.db import migrations


def rename_os_type_name(apps, schema_editor):
    MonitorObjectType = apps.get_model('monitor', 'MonitorObjectType')
    MonitorObjectType.objects.filter(id='os', name='主机资源').update(name='操作系统')


def reverse_rename(apps, schema_editor):
    MonitorObjectType = apps.get_model('monitor', 'MonitorObjectType')
    MonitorObjectType.objects.filter(id='os', name='操作系统').update(name='主机资源')


class Migration(migrations.Migration):

    dependencies = [
        ('monitor', '0058_metric_is_ifmib'),
    ]

    operations = [
        migrations.RunPython(rename_os_type_name, reverse_code=reverse_rename),
    ]
