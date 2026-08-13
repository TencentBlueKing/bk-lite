from django.db import migrations, models
from django.db.models import Count


def ensure_event_channel_unique(apps, schema_editor):
    alias = schema_editor.connection.alias
    ApmAlertOutbox = apps.get_model("apm", "ApmAlertOutbox")
    duplicate = (
        ApmAlertOutbox.objects.using(alias)
        .filter(event_id__isnull=False, channel_id__isnull=False)
        .values("event_id", "channel_id")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
        .order_by("event_id", "channel_id")
        .first()
    )
    if duplicate is not None:
        raise RuntimeError("APM outbox 存在重复 event/channel，请先完成业务核对再迁移")


class Migration(migrations.Migration):
    dependencies = [("apm", "0007_builtin_application")]

    operations = [
        migrations.RunPython(ensure_event_channel_unique, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="apmalertoutbox",
            constraint=models.UniqueConstraint(
                fields=("event", "channel_id"),
                name="apm_outbox_event_channel_portable_unique",
            ),
        ),
    ]
