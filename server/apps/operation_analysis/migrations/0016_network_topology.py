# CUSTOM: WeOps network topology canvas — slim P0 schema.
#
# The original 0016/0017/0018 created 6 tables (NetworkTopology +
# NetworkTopologyWeOpsConnection + 5 detail tables) with a foreign-key
# tree rooted at NetworkTopology. P0 collapses everything into a single
# ``NetworkTopology`` row whose ``view_sets`` JSON carries nodes / links /
# port pairs / metrics / thresholds, and whose ``base_url`` / ``token``
# columns embed the WeOps connection. WeOps detail tables are removed in
# this migration so that the schema matches design.md §6.3 from the first
# forward migrate on a clean database.

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import JSONField


class Migration(migrations.Migration):
    dependencies = [
        ("operation_analysis", "0015_datasource_connector_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="NetworkTopology",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                ("updated_by_domain", models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain")),
                ("groups", JSONField(blank=True, default=list, help_text="组织", null=True)),
                ("name", models.CharField(max_length=128, unique=True, verbose_name="网络拓扑名称")),
                ("desc", models.TextField(blank=True, null=True, verbose_name="描述")),
                ("base_url", models.URLField(max_length=512, verbose_name="WeOps 服务地址")),
                ("token", models.CharField(blank=True, default="", max_length=1024, verbose_name="WeOps 服务 Token（密文存储）")),
                ("refresh_interval", models.PositiveIntegerField(default=60, verbose_name="刷新周期")),
                ("status", models.CharField(choices=[("draft", "草稿"), ("published", "已发布")], default="draft", max_length=32, verbose_name="发布状态")),
                ("view_sets", JSONField(blank=True, default=dict, verbose_name="画布视图集配置")),
                ("last_runtime_cache", JSONField(blank=True, default=dict, verbose_name="最近运行态缓存")),
                ("is_build_in", models.BooleanField(default=False, verbose_name="是否内置")),
                ("build_in_key", models.CharField(blank=True, max_length=255, null=True, unique=True, verbose_name="内置标识键")),
                (
                    "directory",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="network_topologies",
                        to="operation_analysis.directory",
                        verbose_name="所属目录",
                    ),
                ),
            ],
            options={
                "verbose_name": "网络拓扑大屏",
                "db_table": "operation_analysis_network_topology",
            },
        ),
    ]
