import django.db.models.deletion
import django_minio_backend.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operation_analysis", "0025_datasource_transform_config"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExcelMaterializationSlot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                (
                    "role",
                    models.CharField(
                        choices=[("candidate", "候选"), ("success", "当前成功")],
                        default="candidate",
                        max_length=16,
                        verbose_name="槽位角色",
                    ),
                ),
                ("generation", models.PositiveIntegerField(default=0, verbose_name="候选代数")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "待处理"),
                            ("processing", "处理中"),
                            ("succeeded", "成功"),
                            ("failed", "失败"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("source_filename", models.CharField(blank=True, default="", max_length=255, verbose_name="原文件名")),
                (
                    "source_file",
                    models.FileField(
                        blank=True,
                        null=True,
                        storage=django_minio_backend.models.MinioBackend(bucket_name="operation-analysis-private"),
                        upload_to=django_minio_backend.models.iso_date_prefix,
                        verbose_name="原 Excel 文件",
                    ),
                ),
                (
                    "result_file",
                    models.FileField(
                        blank=True,
                        null=True,
                        storage=django_minio_backend.models.MinioBackend(bucket_name="operation-analysis-private"),
                        upload_to=django_minio_backend.models.iso_date_prefix,
                        verbose_name="物化结果文件",
                    ),
                ),
                ("transform_enabled", models.BooleanField(default=False, verbose_name="是否启用转换")),
                ("script_snapshot", models.TextField(blank=True, default="", verbose_name="脚本快照")),
                ("script_hash", models.CharField(blank=True, default="", max_length=64, verbose_name="脚本哈希")),
                ("row_count", models.PositiveIntegerField(default=0, verbose_name="行数")),
                ("field_schema", models.JSONField(blank=True, default=list, verbose_name="字段定义")),
                ("error_code", models.CharField(blank=True, default="", max_length=64, verbose_name="错误码")),
                ("error_summary", models.CharField(blank=True, default="", max_length=512, verbose_name="错误摘要")),
                (
                    "datasource",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="excel_slots",
                        to="operation_analysis.datasourceapimodel",
                        verbose_name="数据源",
                    ),
                ),
            ],
            options={
                "verbose_name": "Excel 物化槽位",
                "db_table": "operation_analysis_excel_materialization_slot",
            },
        ),
        migrations.AddIndex(
            model_name="excelmaterializationslot",
            index=models.Index(fields=["datasource", "role", "-id"], name="oa_excel_slot_role_idx"),
        ),
        migrations.AddIndex(
            model_name="excelmaterializationslot",
            index=models.Index(fields=["datasource", "generation"], name="oa_excel_slot_gen_idx"),
        ),
        migrations.AddField(
            model_name="datasourceapimodel",
            name="excel_candidate_slot",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="operation_analysis.excelmaterializationslot",
                verbose_name="Excel 当前候选槽位",
            ),
        ),
        migrations.AddField(
            model_name="datasourceapimodel",
            name="excel_materialization_generation",
            field=models.PositiveIntegerField(default=0, verbose_name="Excel 物化代数"),
        ),
        migrations.AddField(
            model_name="datasourceapimodel",
            name="excel_success_slot",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="operation_analysis.excelmaterializationslot",
                verbose_name="Excel 当前成功槽位",
            ),
        ),
    ]
