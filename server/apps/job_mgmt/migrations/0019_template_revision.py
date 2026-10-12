import django.db.models.deletion
import django.utils.timezone
import django_minio_backend.models
from django.db import migrations, models

import apps.job_mgmt.models.template_revision


class Migration(migrations.Migration):
    dependencies = [
        ("job_mgmt", "0018_jobexecution_converge_deadline"),
    ]

    operations = [
        migrations.CreateModel(
            name="ScriptRevision",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(max_length=32, verbose_name="版本号")),
                ("name", models.CharField(max_length=128, verbose_name="脚本名称")),
                ("description", models.TextField(blank=True, default="", verbose_name="描述")),
                (
                    "script_type",
                    models.CharField(
                        choices=[("shell", "Shell"), ("python", "Python"), ("powershell", "PowerShell"), ("bat", "Batch")],
                        max_length=32,
                        verbose_name="脚本类型",
                    ),
                ),
                ("content", models.TextField(verbose_name="脚本内容")),
                ("params", models.JSONField(default=list, verbose_name="参数定义")),
                ("timeout", models.IntegerField(default=60, verbose_name="超时时间")),
                ("content_hash", models.CharField(max_length=64, verbose_name="内容摘要")),
                ("created_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now, verbose_name="版本时间")),
                ("created_by", models.CharField(blank=True, default="", max_length=32, verbose_name="操作人")),
                (
                    "script",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="revisions",
                        to="job_mgmt.script",
                        verbose_name="脚本",
                    ),
                ),
            ],
            options={
                "verbose_name": "脚本版本",
                "verbose_name_plural": "脚本版本",
                "db_table": "job_script_revision",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="PlaybookRevision",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(max_length=32, verbose_name="版本号")),
                ("name", models.CharField(max_length=128, verbose_name="Playbook名称")),
                ("description", models.TextField(blank=True, default="", verbose_name="描述")),
                ("version", models.CharField(default="v1.0.0", max_length=32, verbose_name="语义版本号")),
                ("readme", models.TextField(blank=True, default="", verbose_name="README内容")),
                ("file_list", models.JSONField(default=list, verbose_name="文件列表")),
                ("params", models.JSONField(default=list, verbose_name="参数定义")),
                ("file_sha256", models.CharField(blank=True, default="", max_length=64, verbose_name="压缩包摘要")),
                ("content_hash", models.CharField(max_length=64, verbose_name="内容摘要")),
                (
                    "file",
                    models.FileField(
                        blank=True,
                        null=True,
                        storage=django_minio_backend.models.MinioBackend(bucket_name="job-mgmt-private"),
                        upload_to=apps.job_mgmt.models.template_revision.playbook_revision_upload_path,
                        verbose_name="Playbook文件",
                    ),
                ),
                ("created_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now, verbose_name="版本时间")),
                ("created_by", models.CharField(blank=True, default="", max_length=32, verbose_name="操作人")),
                (
                    "playbook",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="revisions",
                        to="job_mgmt.playbook",
                        verbose_name="Playbook",
                    ),
                ),
            ],
            options={
                "verbose_name": "Playbook版本",
                "verbose_name_plural": "Playbook版本",
                "db_table": "job_playbook_revision",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="scriptrevision",
            constraint=models.UniqueConstraint(fields=("script", "label"), name="uniq_job_script_revision_label"),
        ),
        migrations.AddConstraint(
            model_name="playbookrevision",
            constraint=models.UniqueConstraint(fields=("playbook", "label"), name="uniq_job_playbook_revision_label"),
        ),
    ]
