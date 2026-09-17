from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0069_monitorplugin_pack_version"),
    ]

    operations = [
        migrations.AddField(
            model_name="monitorpolicy",
            name="compare_mode",
            field=models.CharField(
                blank=True,
                default="absolute",
                max_length=32,
                verbose_name="比较基准",
            ),
        ),
        migrations.AddField(
            model_name="monitorpolicy",
            name="compare_value_kind",
            field=models.CharField(
                blank=True,
                default="",
                max_length=16,
                verbose_name="比较值类型",
            ),
        ),
        migrations.AddField(
            model_name="monitorpolicy",
            name="count_predicate",
            field=models.JSONField(default=dict, verbose_name="条件计数内阈"),
        ),
        migrations.AddField(
            model_name="monitorpolicy",
            name="forecast_target",
            field=models.FloatField(
                blank=True, null=True, verbose_name="容量线目标"
            ),
        ),
        migrations.AddField(
            model_name="monitorpolicy",
            name="forecast_lookback",
            field=models.JSONField(default=dict, verbose_name="斜率回看窗"),
        ),
        migrations.AddField(
            model_name="monitorpolicy",
            name="recovery_threshold",
            field=models.JSONField(default=dict, verbose_name="恢复阈值"),
        ),
    ]
