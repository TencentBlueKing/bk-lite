import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("log", "0021_userhabit"),
    ]

    operations = [
        migrations.CreateModel(
            name="K8sCollectSetting",
            fields=[
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time"),
                ),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                (
                    "updated_by_domain",
                    models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain"),
                ),
                (
                    "collect_instance",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="k8s_setting",
                        serialize=False,
                        to="log.collectinstance",
                        verbose_name="采集实例",
                    ),
                ),
                ("runtime_profile", models.CharField(max_length=20, verbose_name="运行环境")),
                (
                    "host_log_path",
                    models.CharField(blank=True, default="", max_length=500, verbose_name="节点 Pod 日志根目录"),
                ),
                (
                    "docker_container_log_path",
                    models.CharField(blank=True, default="", max_length=500, verbose_name="Docker 容器日志目录"),
                ),
                ("namespace_patterns", models.JSONField(default=list, verbose_name="采集 Namespace")),
                ("pod_patterns", models.JSONField(default=list, verbose_name="采集 Pod")),
            ],
            options={
                "verbose_name": "K8s 日志采集配置",
                "verbose_name_plural": "K8s 日志采集配置",
                "db_table": "log_k8s_collect_setting",
            },
        ),
    ]
