from datetime import timedelta

from django.db import migrations, models


def backfill_expire_at(apps, schema_editor):
    """存量记录统一回填：expire_at = created_at + 7 天。"""
    DistributionFile = apps.get_model("job_mgmt", "DistributionFile")
    for df in DistributionFile.objects.all().iterator():
        df.expire_at = df.created_at + timedelta(days=7)
        df.save(update_fields=["expire_at"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("job_mgmt", "0008_jobexecution_playbook_version"),
    ]

    operations = [
        migrations.AddField(
            model_name="distributionfile",
            name="expire_at",
            field=models.DateTimeField(db_index=True, null=True, verbose_name="过期时间"),
        ),
        migrations.RunPython(backfill_expire_at, noop_reverse),
        migrations.AlterField(
            model_name="distributionfile",
            name="expire_at",
            field=models.DateTimeField(db_index=True, verbose_name="过期时间"),
        ),
        migrations.RemoveField(
            model_name="distributionfile",
            name="is_permanent",
        ),
    ]
