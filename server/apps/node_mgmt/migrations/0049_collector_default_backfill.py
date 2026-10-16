from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("node_mgmt", "0048_packageversion_publish_status"),
    ]

    operations = [
        migrations.CreateModel(
            name="CollectorDefaultBackfill",
            fields=[
                ("status", models.CharField(default="pending", max_length=16, verbose_name="状态")),
                ("attempts", models.PositiveSmallIntegerField(default=0, verbose_name="连续无进展次数")),
                ("cursor_id", models.CharField(blank=True, default="", max_length=100, verbose_name="续跑节点")),
                ("saw_failure", models.BooleanField(default=False, verbose_name="本轮出现失败")),
                ("locked_at", models.DateTimeField(blank=True, null=True, verbose_name="领取时间")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                (
                    "collector",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="default_backfill",
                        serialize=False,
                        to="node_mgmt.collector",
                        verbose_name="采集器",
                    ),
                ),
            ],
            options={
                "verbose_name": "采集器默认配置补齐",
                "verbose_name_plural": "采集器默认配置补齐",
                "indexes": [models.Index(fields=["status", "created_at"], name="node_backfill_status_created")],
            },
        ),
    ]
