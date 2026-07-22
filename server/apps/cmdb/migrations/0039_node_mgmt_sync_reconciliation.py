import uuid

import django.db.models.deletion
from django.db import migrations, models
from django.utils import timezone


def consolidate_node_mgmt_sync_state(apps, schema_editor):
    config_model = apps.get_model("cmdb", "NodeMgmtSyncConfig")
    run_model = apps.get_model("cmdb", "NodeMgmtSyncRun")

    configs = config_model.objects.order_by("created_at", "id")
    keeper = configs.first()
    if keeper is not None:
        run_model.objects.exclude(task_id=keeper.id).update(task_id=keeper.id)
        configs.exclude(id=keeper.id).delete()
        keeper.singleton_key = "default"
        keeper.save(update_fields=["singleton_key"])

    migrated_at = timezone.now()
    for run in run_model.objects.all().iterator():
        run.generation = uuid.uuid4()
        update_fields = ["generation"]
        if run.status == "running":
            # 旧运行记录没有租约与截止时间，部署后不能继续占用新的全局执行锁。
            run.status = "timeout"
            run.active_scope = None
            run.deadline_at = migrated_at
            run.finished_at = migrated_at
            update_fields.extend(["status", "active_scope", "deadline_at", "finished_at"])
        run.save(update_fields=update_fields)


class Migration(migrations.Migration):
    dependencies = [("cmdb", "0038_change_record_mirror_outbox")]

    operations = [
        migrations.AddField(model_name="nodemgmtsyncconfig", name="singleton_key", field=models.CharField(editable=False, max_length=32, null=True),),
        migrations.AddField(model_name="nodemgmtsyncconfig", name="version", field=models.PositiveBigIntegerField(default=1),),
        migrations.AddField(model_name="nodemgmtsyncconfig", name="schedule_status", field=models.CharField(default="reconciling", max_length=32),),
        migrations.AddField(
            model_name="nodemgmtsyncconfig", name="node_config_status", field=models.CharField(default="reconciling", max_length=32),
        ),
        migrations.AddField(model_name="nodemgmtsyncconfig", name="last_reconciled_at", field=models.DateTimeField(blank=True, null=True),),
        migrations.AddField(
            model_name="nodemgmtsyncconfig", name="reconcile_error_code", field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="nodemgmtsyncconfig", name="reconcile_error_message", field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AlterField(
            model_name="nodemgmtsyncrun",
            name="status",
            field=models.CharField(
                choices=[
                    ("waiting_sync", "等待同步"),
                    ("running", "运行中"),
                    ("submitted", "已提交"),
                    ("success", "成功"),
                    ("partial_success", "部分成功"),
                    ("blocked", "已阻塞"),
                    ("failed", "失败"),
                    ("timeout", "超时"),
                ],
                default="running",
                max_length=32,
                verbose_name="执行状态",
            ),
        ),
        migrations.AddField(model_name="nodemgmtsyncrun", name="generation", field=models.UUIDField(editable=False, null=True),),
        migrations.AddField(model_name="nodemgmtsyncrun", name="active_scope", field=models.CharField(blank=True, max_length=32, null=True),),
        migrations.AddField(model_name="nodemgmtsyncrun", name="reason_code", field=models.CharField(blank=True, default="", max_length=64),),
        migrations.AddField(model_name="nodemgmtsyncrun", name="submitted_at", field=models.DateTimeField(blank=True, null=True),),
        migrations.AddField(model_name="nodemgmtsyncrun", name="heartbeat_at", field=models.DateTimeField(blank=True, null=True),),
        migrations.AddField(model_name="nodemgmtsyncrun", name="deadline_at", field=models.DateTimeField(blank=True, null=True),),
        migrations.RunPython(consolidate_node_mgmt_sync_state, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="nodemgmtsyncconfig",
            name="singleton_key",
            field=models.CharField(default="default", editable=False, max_length=32, unique=True),
        ),
        migrations.AlterField(
            model_name="nodemgmtsyncrun", name="generation", field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name="nodemgmtsyncrun", name="active_scope", field=models.CharField(blank=True, max_length=32, null=True, unique=True),
        ),
        migrations.CreateModel(
            name="NodeMgmtSyncRegionState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("scope_key", models.CharField(max_length=160, unique=True)),
                ("cloud_region_id", models.CharField(max_length=64)),
                ("config_version", models.PositiveBigIntegerField(default=1)),
                ("status", models.CharField(default="pending", max_length=32)),
                ("reason_code", models.CharField(blank=True, default="", max_length=64)),
                ("error_message", models.CharField(blank=True, default="", max_length=255)),
                ("child_execution_id", models.CharField(blank=True, default="", max_length=64)),
                ("node_config_status", models.CharField(default="pending", max_length=32)),
                ("instance_count", models.PositiveIntegerField(default=0)),
                ("submitted_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("collect_task", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="cmdb.collectmodels",),),
                (
                    "config",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="region_states", to="cmdb.nodemgmtsyncconfig",),
                ),
                (
                    "run",
                    models.ForeignKey(
                        blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="region_states", to="cmdb.nodemgmtsyncrun",
                    ),
                ),
            ],
            options={"verbose_name": "节点管理同步区域状态", "verbose_name_plural": "节点管理同步区域状态",},
        ),
    ]
