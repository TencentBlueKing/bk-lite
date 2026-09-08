from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0063_remove_policy_template_scope_name_unique"),
    ]

    operations = [
        migrations.AddField(
            model_name="monitorinstance",
            name="k8s_daemonset_tolerations",
            field=models.JSONField(
                blank=True,
                default=None,
                null=True,
                verbose_name="K8s DaemonSet 污点容忍清单",
            ),
        ),
    ]
