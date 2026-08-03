from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0052_merge_metric_view_query_and_policy_template"),
    ]

    operations = [
        migrations.AddField(
            model_name="metric",
            name="view_config",
            field=models.JSONField(blank=True, default=dict, verbose_name="指标卡视图展示配置"),
        ),
    ]
