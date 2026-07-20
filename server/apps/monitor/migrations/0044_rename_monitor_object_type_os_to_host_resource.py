"""将监控对象分类「操作系统」更名为「主机资源」。

视图层 (apps.monitor.views.monitor_object) 优先从 i18n 读取 type 显示名,
i18n 缺失时回退到 MonitorObjectType.name;为避免 admin 等其它入口仍展示旧值,
同步更新 DB 兜底字段。
"""
from django.db import migrations


def rename_os_type_name(apps, schema_editor):
    MonitorObjectType = apps.get_model('monitor', 'MonitorObjectType')
    MonitorObjectType.objects.filter(id='os', name='操作系统').update(name='主机资源')


def reverse_rename(apps, schema_editor):
    MonitorObjectType = apps.get_model('monitor', 'MonitorObjectType')
    MonitorObjectType.objects.filter(id='os', name='主机资源').update(name='操作系统')


class Migration(migrations.Migration):

    dependencies = [
        ('monitor', '0043_collect_detect_task_and_capability'),
    ]

    operations = [
        migrations.RunPython(rename_os_type_name, reverse_code=reverse_rename),
    ]
