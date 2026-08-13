from django.db import migrations, models
from django.db.models import Count


def _ensure_running_unique(model, relation_field, alias):
    runs = model.objects.using(alias)
    duplicate = (
        runs.filter(status="running")
        .values(f"{relation_field}_id")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
        .order_by(f"{relation_field}_id")
        .first()
    )
    if duplicate is not None:
        raise RuntimeError(f"{model._meta.label} 存在重复运行记录，请先完成业务核对再迁移")


def ensure_running_runs_unique(apps, schema_editor):
    alias = schema_editor.connection.alias
    _ensure_running_unique(apps.get_model("system_mgmt", "UserSyncRun"), "source", alias)
    _ensure_running_unique(apps.get_model("system_mgmt", "IMNotificationSyncRun"), "channel", alias)


def _populate_running_guard(model, alias):
    runs = model.objects.using(alias)
    runs.filter(status="running").update(running_guard=True)


def populate_running_guards(apps, schema_editor):
    alias = schema_editor.connection.alias
    _populate_running_guard(apps.get_model("system_mgmt", "UserSyncRun"), alias)
    _populate_running_guard(apps.get_model("system_mgmt", "IMNotificationSyncRun"), alias)


def clear_running_guards(apps, schema_editor):
    alias = schema_editor.connection.alias
    apps.get_model("system_mgmt", "UserSyncRun").objects.using(alias).update(running_guard=None)
    apps.get_model("system_mgmt", "IMNotificationSyncRun").objects.using(alias).update(running_guard=None)


class Migration(migrations.Migration):
    dependencies = [("system_mgmt", "0044_remove_builtin_webhook_domains")]

    operations = [
        migrations.RunPython(ensure_running_runs_unique, migrations.RunPython.noop),
        migrations.AddField(
            model_name="usersyncrun",
            name="running_guard",
            field=models.BooleanField(default=None, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="imnotificationsyncrun",
            name="running_guard",
            field=models.BooleanField(default=None, editable=False, null=True),
        ),
        migrations.RunPython(populate_running_guards, clear_running_guards),
        migrations.AddConstraint(
            model_name="usersyncrun",
            constraint=models.UniqueConstraint(
                fields=("source", "running_guard"),
                name="uniq_user_sync_run_guard_per_source",
            ),
        ),
        migrations.AddConstraint(
            model_name="imnotificationsyncrun",
            constraint=models.UniqueConstraint(
                fields=("channel", "running_guard"),
                name="uniq_im_sync_run_guard_per_channel",
            ),
        ),
    ]
