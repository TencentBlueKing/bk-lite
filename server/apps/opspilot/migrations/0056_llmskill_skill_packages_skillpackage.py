from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("opspilot", "0055_rename_memory_mgmt_organiz_a1b2c3_idx_memory_mgmt_organiz_0c67ee_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="llmskill",
            name="skill_packages",
            field=models.JSONField(default=list, verbose_name="技能包"),
        ),
        migrations.CreateModel(
            name="SkillPackage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                ("updated_by_domain", models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                ("package_id", models.CharField(db_index=True, max_length=128, verbose_name="技能包ID")),
                ("name", models.CharField(max_length=255, verbose_name="名称")),
                ("version", models.CharField(default="0.1.0", max_length=64, verbose_name="版本")),
                ("description", models.TextField(blank=True, default="", verbose_name="描述")),
                ("category", models.CharField(blank=True, default="", max_length=128, verbose_name="分类")),
                ("source_type", models.CharField(default="zip", max_length=32, verbose_name="来源类型")),
                ("source_url", models.TextField(blank=True, default="", verbose_name="来源地址")),
                ("storage_path", models.TextField(blank=True, default="", verbose_name="存储路径")),
                ("manifest", models.JSONField(default=dict, verbose_name="技能包清单")),
                ("skill_markdown", models.TextField(blank=True, default="", verbose_name="技能说明")),
                ("required_tools", models.JSONField(default=list, verbose_name="依赖工具")),
                ("triggers", models.JSONField(default=list, verbose_name="触发词")),
                ("team", models.JSONField(default=list, verbose_name="分组")),
                ("is_enabled", models.BooleanField(default=True, verbose_name="是否启用")),
            ],
            options={
                "db_table": "model_provider_mgmt_skillpackage",
                "unique_together": {("package_id", "version", "domain")},
            },
        ),
    ]
