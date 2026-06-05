from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("opspilot", "0053_workflowattachmentasset"),
    ]

    operations = [
        migrations.CreateModel(
            name="MemoryWriteCache",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("workflow_id", models.IntegerField(db_index=True, verbose_name="工作流ID")),
                ("node_id", models.CharField(db_index=True, max_length=100, verbose_name="节点ID")),
                ("memory_target_id", models.CharField(db_index=True, max_length=255, verbose_name="记忆对象ID")),
                ("content", models.TextField(verbose_name="缓存内容")),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "待处理"), ("processing", "处理中")],
                        db_index=True,
                        default="pending",
                        max_length=20,
                        verbose_name="状态",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="创建时间")),
            ],
            options={
                "verbose_name": "记忆写入缓存",
                "verbose_name_plural": "记忆写入缓存",
                "db_table": "memory_mgmt_memorywritecache",
            },
        ),
        migrations.AddIndex(
            model_name="memorywritecache",
            index=models.Index(
                fields=["workflow_id", "node_id", "memory_target_id", "status", "created_at"],
                name="memory_mgmt_workflo_55002b_idx",
            ),
        ),
    ]
