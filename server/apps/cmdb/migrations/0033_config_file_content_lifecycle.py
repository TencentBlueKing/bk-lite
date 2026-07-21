from django.db import migrations, models
from django.db.models import Q


def initialize_content_lifecycle(apps, _schema_editor):
    config_file_version = apps.get_model("cmdb", "ConfigFileVersion")
    versions_with_content = config_file_version.objects.exclude(Q(content="") | Q(content__isnull=True))
    versions_with_content.update(content_status="ready", content_error="")
    config_file_version.objects.filter(Q(content="") | Q(content__isnull=True)).update(
        content_status="error",
        content_error="历史配置版本缺少正文对象",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0032_dedupe_config_file_versions"),
    ]

    operations = [
        migrations.AddField(
            model_name="configfileversion",
            name="content_attempt_count",
            field=models.PositiveIntegerField(default=0, help_text="正文生命周期处理尝试次数"),
        ),
        migrations.AddField(
            model_name="configfileversion",
            name="content_error",
            field=models.TextField(blank=True, default="", help_text="正文发布或删除失败摘要"),
        ),
        migrations.AddField(
            model_name="configfileversion",
            name="content_status",
            field=models.CharField(
                choices=[
                    ("pending", "待发布"),
                    ("ready", "可用"),
                    ("delete_pending", "待删除"),
                    ("error", "处理失败"),
                ],
                default="pending",
                help_text="配置正文跨存储生命周期状态",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="configfileversion",
            name="content_updated_at",
            field=models.DateTimeField(auto_now=True, help_text="正文生命周期状态更新时间"),
        ),
        migrations.AddField(
            model_name="configfileversion",
            name="temp_content_key",
            field=models.CharField(blank=True, default="", help_text="待发布的临时对象键", max_length=512),
        ),
        migrations.RunPython(initialize_content_lifecycle, migrations.RunPython.noop),
        migrations.AddIndex(
            model_name="configfileversion",
            index=models.Index(fields=["content_status", "content_updated_at"], name="cfg_content_state_idx"),
        ),
    ]
