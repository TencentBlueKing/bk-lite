from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0060_subscription_attribute_lifecycle"),
    ]

    operations = [
        migrations.CreateModel(
            name="AutoRelationPending",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("instance_id", models.BigIntegerField(null=True, unique=True)),
                ("model_asst_id", models.CharField(max_length=255, null=True, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "cmdb_auto_relation_pending",
                "constraints": [
                    models.CheckConstraint(
                        check=models.Q(
                            models.Q(("instance_id__isnull", False), ("model_asst_id__isnull", True)),
                            models.Q(("instance_id__isnull", True), ("model_asst_id__isnull", False)),
                            _connector="OR",
                        ),
                        name="cmdb_auto_relation_pending_one_target",
                    )
                ],
            },
        ),
    ]
