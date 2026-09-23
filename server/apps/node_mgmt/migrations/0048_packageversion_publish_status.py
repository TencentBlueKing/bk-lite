from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("node_mgmt", "0047_urldecode_custom_pull_env_password"),
    ]

    operations = [
        migrations.AddField(
            model_name="packageversion",
            name="status",
            field=models.CharField(
                choices=[("pending", "pending"), ("ready", "ready"), ("deleting", "deleting")],
                db_index=True,
                default="ready",
                max_length=16,
                verbose_name="发布状态",
            ),
        ),
    ]
