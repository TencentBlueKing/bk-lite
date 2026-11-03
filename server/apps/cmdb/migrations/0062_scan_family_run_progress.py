import django.db.models.deletion
from django.db import migrations, models

OPEN_EXECUTION_STATUSES = ("pending", "running", "finalizing")
HOST_MAX_LENGTH = 64


def copy_open_progress_hosts(apps, schema_editor):
    """把未结束执行里的 progress_hosts 逐条写入进度表，不改 received_count。"""
    using = schema_editor.connection.alias
    family_run_model = apps.get_model("cmdb", "ScanFamilyRun")
    progress_model = apps.get_model("cmdb", "ScanFamilyRunProgress")
    runs = (
        family_run_model.objects.using(using)
        .filter(execution__status__in=OPEN_EXECUTION_STATUSES)
        .only("id", "progress_hosts")
        .iterator()
    )
    for run in runs:
        hosts = run.progress_hosts or []
        if not isinstance(hosts, list):
            continue
        for item in hosts:
            if item is None:
                continue
            host = str(item).strip()
            if not host:
                continue
            if len(host) > HOST_MAX_LENGTH:
                host = host[:HOST_MAX_LENGTH]
            progress_model.objects.using(using).get_or_create(family_run_id=run.id, host=host)


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0061_showfield_created_by_model_unique"),
    ]

    operations = [
        migrations.CreateModel(
            name="ScanFamilyRunProgress",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("host", models.CharField(max_length=64)),
                (
                    "family_run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="progress_entries",
                        to="cmdb.scanfamilyrun",
                    ),
                ),
            ],
            options={
                "verbose_name": "扫描族进度地址",
                "verbose_name_plural": "扫描族进度地址",
                "unique_together": {("family_run", "host")},
            },
        ),
        migrations.RunPython(copy_open_progress_hosts, migrations.RunPython.noop),
    ]
