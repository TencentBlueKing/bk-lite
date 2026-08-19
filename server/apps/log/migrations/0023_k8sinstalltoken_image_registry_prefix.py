from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("log", "0022_k8scollectsetting")]

    operations = [
        migrations.AddField(
            model_name="k8sinstalltoken",
            name="image_registry_prefix",
            field=models.CharField(
                default="bk-lite.tencentcloudcr.com/bklite",
                max_length=255,
                verbose_name="镜像仓库前缀",
            ),
        ),
    ]
