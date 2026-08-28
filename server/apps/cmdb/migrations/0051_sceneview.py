from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0050_alter_collectmodels_timeout"),
    ]

    operations = [
        migrations.CreateModel(
            name="SceneView",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                (
                    "updated_by_domain",
                    models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain"),
                ),
                ("name", models.CharField(max_length=128, verbose_name="视图名称")),
                (
                    "visibility",
                    models.CharField(
                        choices=[("personal", "个人"), ("organization", "组织共享"), ("global", "全局")],
                        db_index=True,
                        default="personal",
                        max_length=20,
                        verbose_name="可见范围",
                    ),
                ),
                (
                    "organization",
                    models.BigIntegerField(blank=True, db_index=True, null=True, verbose_name="组织共享所属组织ID"),
                ),
                ("model_ids", models.JSONField(default=list, verbose_name="模型范围")),
                ("tags", models.JSONField(default=list, verbose_name="标签条件")),
                (
                    "tag_match",
                    models.CharField(
                        choices=[("and", "AND"), ("or", "OR")],
                        default="and",
                        max_length=8,
                        verbose_name="标签匹配",
                    ),
                ),
            ],
            options={
                "verbose_name": "标签视图",
                "verbose_name_plural": "标签视图",
                "db_table": "cmdb_scene_view",
                "ordering": ["-updated_at"],
            },
        ),
        migrations.AddIndex(
            model_name="sceneview",
            index=models.Index(fields=["created_by", "domain", "visibility"], name="idx_scene_owner_vis"),
        ),
        migrations.AddIndex(
            model_name="sceneview",
            index=models.Index(fields=["visibility", "organization"], name="idx_scene_vis_org"),
        ),
    ]
