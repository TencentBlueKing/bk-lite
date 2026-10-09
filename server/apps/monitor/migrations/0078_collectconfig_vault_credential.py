from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0077_monitorpolicy_compare_span"),
    ]

    operations = [
        migrations.AddField(
            model_name="collectconfig",
            name="vault_credential_id",
            field=models.CharField(db_index=True, default="", max_length=128, verbose_name="凭据仓库 ID"),
        ),
        migrations.AddField(
            model_name="collectconfig",
            name="vault_variant",
            field=models.CharField(default="", max_length=32, verbose_name="凭据分支"),
        ),
        migrations.AddField(
            model_name="collectconfig",
            name="vault_actor_context",
            field=models.JSONField(default=dict, verbose_name="凭据绑定人"),
        ),
        migrations.AddField(
            model_name="collectconfig",
            name="vault_credential_name",
            field=models.CharField(default="", max_length=128, verbose_name="凭据名称快照"),
        ),
        migrations.AddField(
            model_name="collectconfig",
            name="vault_applied_version",
            field=models.PositiveIntegerField(default=0, verbose_name="已下发凭据版本"),
        ),
        migrations.AddField(
            model_name="collectconfig",
            name="vault_sync_error",
            field=models.CharField(default="", max_length=32, verbose_name="凭据同步错误码"),
        ),
        migrations.AddField(
            model_name="collectconfig",
            name="vault_synced_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="凭据下发时间"),
        ),
    ]
