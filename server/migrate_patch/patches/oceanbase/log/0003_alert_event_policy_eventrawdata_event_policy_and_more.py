# OceanBase 数据库兼容补丁
# 原始文件: apps/log/migrations/0003_alert_event_policy_eventrawdata_event_policy_and_more.py
# 问题:
#   EventRawData.data 字段在后续迁移中变更类型:
#     0003: JSONField(default=dict) → 0004: JSONField(default=list) → 0009: S3JSONField
#   OceanBase 不支持 "Alter non string type not supported" (错误码 1235)
# 方案:
#   在初始创建时直接定义为最终类型 S3JSONField，后续 0004/0009 使用 FakeAlterField 跳过

import django.db.models.deletion
from django.db import migrations, models

import apps.core.fields.s3_json_field


class Migration(migrations.Migration):
    dependencies = [
        ("log", "0002_streamcollectinstance"),
    ]

    operations = [
        migrations.CreateModel(
            name="Alert",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("id", models.CharField(max_length=50, primary_key=True, serialize=False, verbose_name="告警ID")),
                ("source_id", models.CharField(db_index=True, max_length=100, verbose_name="资源ID")),
                ("level", models.CharField(db_index=True, default="", max_length=20, verbose_name="最高告警级别")),
                ("value", models.FloatField(blank=True, null=True, verbose_name="最高告警值")),
                ("content", models.TextField(blank=True, verbose_name="告警内容")),
                ("status", models.CharField(db_index=True, default="new", max_length=20, verbose_name="告警状态")),
                ("start_event_time", models.DateTimeField(blank=True, null=True, verbose_name="开始事件时间")),
                ("end_event_time", models.DateTimeField(blank=True, null=True, verbose_name="结束事件时间")),
                ("operator", models.CharField(blank=True, max_length=50, null=True, verbose_name="告警处理人")),
                ("info_event_count", models.IntegerField(default=0, verbose_name="正常事件计数")),
                ("collect_type", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="log.collecttype", verbose_name="采集方式")),
            ],
            options={
                "verbose_name": "告警记录",
                "verbose_name_plural": "告警记录",
            },
        ),
        migrations.CreateModel(
            name="Event",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("id", models.CharField(max_length=50, primary_key=True, serialize=False, verbose_name="事件ID")),
                ("source_id", models.CharField(db_index=True, max_length=100, verbose_name="资源ID")),
                ("event_time", models.DateTimeField(blank=True, null=True, verbose_name="事件发生时间")),
                ("value", models.FloatField(blank=True, null=True, verbose_name="事件值")),
                ("level", models.CharField(max_length=20, verbose_name="事件级别")),
                ("content", models.TextField(blank=True, verbose_name="事件内容")),
                ("notice_result", models.JSONField(default=list, verbose_name="通知结果")),
                ("alert", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="log.alert", verbose_name="关联告警")),
            ],
            options={
                "verbose_name": "事件记录",
                "verbose_name_plural": "事件记录",
            },
        ),
        migrations.CreateModel(
            name="Policy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                ("updated_by_domain", models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain")),
                ("name", models.CharField(max_length=255, verbose_name="策略名称")),
                ("organizations", models.JSONField(default=list, verbose_name="所属组织")),
                ("last_run_time", models.DateTimeField(blank=True, null=True, verbose_name="最后一次执行时间")),
                ("alert_type", models.CharField(max_length=50, verbose_name="告警类型")),
                ("alert_name", models.CharField(max_length=255, verbose_name="告警名称")),
                ("alert_level", models.CharField(max_length=30, verbose_name="告警等级")),
                ("alert_condition", models.JSONField(default=dict, verbose_name="告警条件")),
                ("schedule", models.JSONField(default=dict, verbose_name="策略执行周期, eg: 1h执行一次, 5m执行一次")),
                ("period", models.JSONField(default=dict, verbose_name="每次监控检测的数据周期,eg: 1h内, 5m内")),
                ("notice", models.BooleanField(default=True, verbose_name="是否通知")),
                ("notice_type", models.CharField(default="", max_length=50, verbose_name="通知方式")),
                ("notice_type_id", models.IntegerField(default=0, verbose_name="通知方式ID")),
                ("notice_users", models.JSONField(default=list, verbose_name="通知人")),
                ("enable", models.BooleanField(default=True, verbose_name="是否启用")),
                ("collect_type", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="log.collecttype", verbose_name="采集方式")),
            ],
            options={
                "verbose_name": "告警策略",
                "verbose_name_plural": "告警策略",
                "unique_together": {("name", "collect_type")},
            },
        ),
        migrations.CreateModel(
            name="EventRawData",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                # --- OceanBase 补丁: 直接定义为最终类型 S3JSONField ---
                # 原始: models.JSONField(default=dict, verbose_name='原始数据')
                # 后续变更: 0004 → JSONField(default=list), 0009 → S3JSONField
                # OceanBase 不支持 AlterField 变更 JSON 类型字段，故在此直接定义最终类型
                (
                    "data",
                    apps.core.fields.s3_json_field.S3JSONField(
                        bucket_name="log-alert-raw-data",
                        compressed=True,
                        help_text="自动压缩并存储到 MinIO/S3",
                        max_length=500,
                        upload_to=apps.core.fields.s3_json_field.s3_json_upload_path,
                        verbose_name="原始数据",
                    ),
                ),
                ("event", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="log.event", verbose_name="事件")),
            ],
            options={
                "verbose_name": "事件原始数据",
                "verbose_name_plural": "事件原始数据",
            },
        ),
        migrations.AddField(
            model_name="event",
            name="policy",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="log.policy", verbose_name="关联策略"),
        ),
        migrations.AddField(
            model_name="alert",
            name="policy",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="log.policy", verbose_name="关联策略"),
        ),
        migrations.CreateModel(
            name="PolicyOrganization",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                ("updated_by_domain", models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain")),
                ("organization", models.IntegerField(verbose_name="组织id")),
                ("policy", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="log.policy", verbose_name="监控策略")),
            ],
            options={
                "verbose_name": "策略组织",
                "verbose_name_plural": "策略组织",
                "unique_together": {("policy", "organization")},
            },
        ),
    ]
