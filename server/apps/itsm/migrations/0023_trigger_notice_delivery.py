from django.db import migrations, models


def fail_unrecoverable_notices(apps, schema_editor):
    logs = apps.get_model("itsm", "TriggerLog").objects.using(schema_editor.connection.alias)
    logs.filter(status="pending", action="notice", delivery_payload__isnull=True).update(
        status="failed",
        message="历史通知缺少投递快照，无法恢复，请核对发送结果",
    )


class Migration(migrations.Migration):
    dependencies = [("itsm", "0022_knowledge_articles")]

    operations = [
        migrations.AddField(
            model_name="triggerlog",
            name="delivery_payload",
            field=models.JSONField(default=None, null=True),
        ),
        migrations.AddField(
            model_name="triggerlog",
            name="delivery_claimed_at",
            field=models.DateTimeField(null=True),
        ),
        migrations.AddField(
            model_name="triggerlog",
            name="delivery_attempts",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="triggerlog",
            name="delivery_receipts",
            field=models.JSONField(default=dict),
        ),
        migrations.AddIndex(
            model_name="triggerlog",
            index=models.Index(fields=["status", "action", "id"], name="itsm_triglog_pending_idx"),
        ),
        migrations.RunPython(fail_unrecoverable_notices, migrations.RunPython.noop),
    ]
