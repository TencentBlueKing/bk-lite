# 达梦数据库兼容补丁
# 原始文件: django_celery_results/migrations/0006_taskresult_date_created.py
# 问题: F() 表达式在达梦上生成的 UPDATE SQL WHERE 子句为空，导致语法错误
# 方案: 使用原生 SQL 替代 ORM 的 F() 表达式更新

import django.utils.timezone
from django.db import connections, migrations, models


def copy_date_done_to_date_created(apps, schema_editor):
    """将 date_done 的值复制到 date_created，兼容达梦数据库"""
    TaskResult = apps.get_model("django_celery_results", "taskresult")
    db_alias = schema_editor.connection.alias
    table_name = TaskResult._meta.db_table

    with connections[db_alias].cursor() as cursor:
        cursor.execute('UPDATE "{table}" SET "DATE_CREATED" = "DATE_DONE"'.format(table=table_name.upper()))


def reverse_copy_date_done_to_date_created(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("django_celery_results", "0005_taskresult_worker"),
    ]

    operations = [
        migrations.AddField(
            model_name="taskresult",
            name="date_created",
            field=models.DateTimeField(
                auto_now_add=True,
                db_index=True,
                default=django.utils.timezone.now,
                help_text="Datetime field when the task result was created in UTC",
                verbose_name="Created DateTime",
            ),
            preserve_default=False,
        ),
        migrations.RunPython(
            copy_date_done_to_date_created,
            reverse_copy_date_done_to_date_created,
        ),
    ]
