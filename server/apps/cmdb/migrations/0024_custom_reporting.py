from django.db import migrations, models
import django.db.models.deletion


def sync_custom_reporting_task_scopes(apps, schema_editor):
    CustomReportingTask = apps.get_model("cmdb", "CustomReportingTask")
    CustomReportingTaskScope = apps.get_model("cmdb", "CustomReportingTaskScope")

    scopes = []
    for task in CustomReportingTask.objects.all().iterator():
        for team_id in task.team or []:
            scopes.append(
                CustomReportingTaskScope(task_id=task.id, team_id=team_id, name=task.name)
            )
    if scopes:
        CustomReportingTaskScope.objects.bulk_create(scopes)


class Migration(migrations.Migration):

    dependencies = [
        ("cmdb", "0023_collecttaskcredentialhit_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="CustomReportingTask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                ("updated_by_domain", models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain")),
                ("name", models.CharField(db_index=True, max_length=128, verbose_name="任务名称")),
                ("team", models.JSONField(default=list, verbose_name="关联组织")),
                ("config", models.JSONField(default=dict, verbose_name="任务配置")),
                ("is_enabled", models.BooleanField(db_index=True, default=True, verbose_name="启用状态")),
                ("last_reported_at", models.DateTimeField(blank=True, db_index=True, null=True, verbose_name="最近上报时间")),
            ],
            options={
                "db_table": "cmdb_custom_reporting_task",
                "verbose_name": "自定义报表任务",
                "verbose_name_plural": "自定义报表任务",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="CustomReportingTaskScope",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("team_id", models.BigIntegerField(db_index=True, verbose_name="组织ID")),
                ("name", models.CharField(max_length=128, verbose_name="任务名称")),
                ("task", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="scopes", to="cmdb.customreportingtask", verbose_name="所属任务")),
            ],
            options={
                "db_table": "cmdb_custom_reporting_task_scope",
                "verbose_name": "自定义报表任务组织映射",
                "verbose_name_plural": "自定义报表任务组织映射",
                "unique_together": {("team_id", "name")},
            },
        ),
        migrations.CreateModel(
            name="CustomReportingBatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("status", models.CharField(choices=[("pending", "待处理"), ("running", "执行中"), ("success", "成功"), ("failed", "失败")], db_index=True, default="pending", max_length=32, verbose_name="批次状态")),
                ("summary", models.JSONField(default=dict, verbose_name="批次摘要")),
                ("task", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="batches", to="cmdb.customreportingtask", verbose_name="所属任务")),
            ],
            options={
                "db_table": "cmdb_custom_reporting_batch",
                "verbose_name": "自定义报表批次",
                "verbose_name_plural": "自定义报表批次",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="CustomReportingCredential",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                ("updated_by_domain", models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain")),
                ("name", models.CharField(max_length=128, verbose_name="凭据名称")),
                ("credential_type", models.CharField(max_length=64, verbose_name="凭据类型")),
                ("credential_data", models.JSONField(default=dict, verbose_name="凭据内容")),
                ("is_enabled", models.BooleanField(default=True, verbose_name="启用状态")),
                ("last_used_at", models.DateTimeField(blank=True, null=True, verbose_name="最近使用时间")),
                ("task", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="credentials", to="cmdb.customreportingtask", verbose_name="所属任务")),
            ],
            options={
                "db_table": "cmdb_custom_reporting_credential",
                "verbose_name": "自定义报表凭据",
                "verbose_name_plural": "自定义报表凭据",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="customreportingcredential",
            constraint=models.UniqueConstraint(fields=("task",), name="uniq_cr_credential_task"),
        ),
        migrations.CreateModel(
            name="CustomReportingPendingRelation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("source_model_id", models.CharField(max_length=64, verbose_name="源模型ID")),
                ("target_model_id", models.CharField(max_length=64, verbose_name="目标模型ID")),
                ("relation_payload", models.JSONField(default=dict, verbose_name="关系载荷")),
                ("task", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="pending_relations", to="cmdb.customreportingtask", verbose_name="所属任务")),
            ],
            options={
                "db_table": "cmdb_custom_reporting_pending_relation",
                "verbose_name": "自定义报表待处理关系",
                "verbose_name_plural": "自定义报表待处理关系",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="CustomReportingCleanupReview",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                ("updated_by_domain", models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain")),
                ("status", models.CharField(choices=[("pending", "待审核"), ("approved", "已通过"), ("rejected", "已驳回")], db_index=True, default="pending", max_length=32, verbose_name="审核状态")),
                ("review_payload", models.JSONField(default=dict, verbose_name="审核内容")),
                ("reviewed_by", models.CharField(blank=True, default="", max_length=32, verbose_name="审核人")),
                ("reviewed_at", models.DateTimeField(blank=True, null=True, verbose_name="审核时间")),
                ("batch", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cleanup_reviews", to="cmdb.customreportingbatch", verbose_name="所属批次")),
            ],
            options={
                "db_table": "cmdb_custom_reporting_cleanup_review",
                "verbose_name": "自定义报表清理审核",
                "verbose_name_plural": "自定义报表清理审核",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="customreportingtaskscope",
            index=models.Index(fields=["task", "team_id"], name="idx_cr_task_scope_task_team"),
        ),
        migrations.RunPython(sync_custom_reporting_task_scopes, migrations.RunPython.noop),
        migrations.AddIndex(
            model_name="customreportingtask",
            index=models.Index(fields=["name"], name="idx_custom_report_task_name"),
        ),
        migrations.AddIndex(
            model_name="customreportingtask",
            index=models.Index(fields=["is_enabled"], name="idx_custom_report_task_enabled"),
        ),
        migrations.AddIndex(
            model_name="customreportingbatch",
            index=models.Index(fields=["task", "status"], name="idx_custom_report_batch_status"),
        ),
        migrations.AddIndex(
            model_name="customreportingpendingrelation",
            index=models.Index(fields=["task", "source_model_id", "target_model_id"], name="idx_cr_pending_rel"),
        ),
        migrations.AddIndex(
            model_name="customreportingcleanupreview",
            index=models.Index(fields=["batch", "status"], name="idx_cr_review_status"),
        ),
        migrations.AlterField(
            model_name="changerecord",
            name="scenario",
            field=models.CharField(
                choices=[
                    ("device_lifecycle", "设备流转"),
                    ("relation_change", "关系变更"),
                    ("ordinary_attribute_change", "普通属性变更"),
                    ("collect_automation_change", "自动采集"),
                    ("model_management_change", "模型管理变更"),
                    ("custom_reporting_change", "自定义报表变更"),
                ],
                db_index=True,
                default="ordinary_attribute_change",
                max_length=40,
                verbose_name="变更场景",
            ),
        ),
    ]
