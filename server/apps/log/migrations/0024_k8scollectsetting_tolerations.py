from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("log", "0023_k8sinstalltoken_image_registry_prefix"),
    ]

    operations = [
        migrations.AddField(
            model_name="k8scollectsetting",
            name="tolerations",
            field=models.JSONField(blank=True, default=None, null=True, verbose_name="DaemonSet 污点容忍"),
        ),
    ]
