from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("log", "0024_logextractor_collect_type_scope"),
    ]

    operations = [
        migrations.AddField(
            model_name="k8scollectsetting",
            name="tolerations",
            field=models.JSONField(
                blank=True,
                default=None,
                null=True,
                verbose_name="DaemonSet 污点容忍清单",
            ),
        ),
        migrations.AddField(
            model_name="k8sinstalltoken",
            name="tolerations",
            field=models.JSONField(
                blank=True,
                default=None,
                null=True,
                verbose_name="DaemonSet 污点容忍清单",
            ),
        ),
    ]
