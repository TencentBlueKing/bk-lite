from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0086_policy_instance_baseline_dimensions"),
    ]

    operations = [
        migrations.CreateModel(
            name="PendingRemoteConfigDeletion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("child_config_ids", models.JSONField(default=list)),
                ("base_config_ids", models.JSONField(default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "monitor_pending_remote_config_deletion",
            },
        ),
    ]
