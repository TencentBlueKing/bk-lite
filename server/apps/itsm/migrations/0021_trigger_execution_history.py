import django.db.models.deletion
from django.db import migrations, models


def snapshot_legacy_trigger_logs(apps, schema_editor):
    trigger_log = apps.get_model("itsm", "TriggerLog")
    manager = trigger_log.objects.using(schema_editor.connection.alias)
    updates = []
    fields = ("domain", "trigger_name", "event", "action")
    for log in manager.filter(trigger__isnull=False).select_related("trigger").iterator(chunk_size=500):
        trigger = log.trigger
        log.domain = trigger.domain
        log.trigger_name = trigger.name
        log.event = trigger.event
        action = log.message.partition(":")[0]
        log.action = action if action in {"tag", "notice", "status"} else trigger.action
        updates.append(log)
        if len(updates) == 500:
            manager.bulk_update(updates, fields)
            updates.clear()
    if updates:
        manager.bulk_update(updates, fields)


class Migration(migrations.Migration):
    dependencies = [("itsm", "0020_ticket_survey_answers")]

    operations = [
        migrations.AddField(
            model_name="triggerlog",
            name="run_id",
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="triggerlog",
            name="trigger_name",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="triggerlog",
            name="event",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="triggerlog",
            name="action",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="triggerlog",
            name="position",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="triggerlog",
            name="status",
            field=models.CharField(
                choices=[("legacy", "历史记录"), ("pending", "处理中"), ("success", "成功"), ("failed", "失败")],
                default="legacy",
                max_length=16,
            ),
        ),
        migrations.RunPython(snapshot_legacy_trigger_logs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="triggerlog",
            name="trigger",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="logs", to="itsm.trigger"),
        ),
        migrations.AddIndex(
            model_name="triggerlog",
            index=models.Index(fields=("ticket_id", "domain", "id"), name="itsm_triglog_ticket_idx"),
        ),
    ]
