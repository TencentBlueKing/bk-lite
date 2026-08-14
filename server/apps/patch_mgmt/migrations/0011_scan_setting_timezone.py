from django.db import migrations, models


def preserve_existing_scan_schedule_timezone(apps, schema_editor):
    scan_setting_model = apps.get_model("patch_mgmt", "ScanSetting")
    periodic_task_model = apps.get_model("django_celery_beat", "PeriodicTask")
    db_alias = schema_editor.connection.alias

    setting = scan_setting_model.objects.using(db_alias).filter(pk=1).first()
    task = periodic_task_model.objects.using(db_alias).filter(name="patch_mgmt_periodic_compliance_scan").select_related("crontab").first()
    if setting is None or task is None or task.crontab is None:
        return

    # 迁移期没有认证用户上下文，不能猜测某个用户的时区。
    # 先保留存量 Celery 调度的真实语义；管理员下次保存时，
    # API 再以 request.user.timezone 更新该快照及调度。
    setting.timezone = str(task.crontab.timezone)
    setting.save(using=db_alias, update_fields=["timezone"])


class Migration(migrations.Migration):
    dependencies = [
        ("django_celery_beat", "0018_improve_crontab_helptext"),
        ("patch_mgmt", "0010_cross_database_kb_guard"),
    ]

    operations = [
        migrations.AddField(
            model_name="scansetting",
            name="timezone",
            field=models.CharField(
                blank=True,
                default="",
                max_length=64,
                verbose_name="调度时区",
            ),
        ),
        migrations.RunPython(
            preserve_existing_scan_schedule_timezone,
            migrations.RunPython.noop,
        ),
    ]
