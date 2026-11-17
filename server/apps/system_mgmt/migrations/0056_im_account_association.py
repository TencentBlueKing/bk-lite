import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


def _clock_parts(sync_time):
    parts = str(sync_time).split(":")
    if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    return str(int(parts[0])), str(int(parts[1]))


def _close_extra_running_runs(run_model, association_id):
    """一条渠道上如果有多条进行中的同步，只留最新一条，否则后面的唯一约束加不上去。"""
    running_ids = list(
        run_model.objects.filter(account_association_id=association_id, status="running").order_by("-started_at", "-id").values_list("id", flat=True)
    )
    if len(running_ids) < 2:
        return
    run_model.objects.filter(id__in=running_ids[1:]).update(
        status="failed",
        running_guard=None,
        finished_at=django.utils.timezone.now(),
    )


def copy_account_associations(apps, schema_editor):
    from apps.system_mgmt.services.account_association_migration import plan_account_associations

    channel_model = apps.get_model("system_mgmt", "IMNotificationChannel")
    mapping_model = apps.get_model("system_mgmt", "IMNotificationUserMapping")
    run_model = apps.get_model("system_mgmt", "IMNotificationSyncRun")
    association_model = apps.get_model("system_mgmt", "IMAccountAssociation")
    periodic_task_model = apps.get_model("django_celery_beat", "PeriodicTask")
    crontab_model = apps.get_model("django_celery_beat", "CrontabSchedule")

    channels = [
        {
            "id": channel.id,
            "integration_instance_id": channel.integration_instance_id,
            "name": channel.name,
            "platform_match_field": channel.platform_match_field,
            "external_match_field": channel.external_match_field,
            "external_receive_field": channel.external_receive_field,
            "schedule_config": channel.schedule_config or {},
            "enabled": channel.enabled,
            "status": channel.status,
            "created_by": channel.created_by,
            "updated_by": channel.updated_by,
            "domain": channel.domain,
            "updated_by_domain": channel.updated_by_domain,
        }
        for channel in channel_model.objects.all().order_by("id")
    ]
    runs = [
        {
            "id": run.id,
            "channel_id": run.channel_id,
            "status": run.status,
            "finished_at": run.finished_at,
        }
        for run in run_model.objects.all().only("id", "channel_id", "status", "finished_at")
    ]
    mapping_ids_by_channel: dict[int, list[int]] = {}
    for mapping in mapping_model.objects.all().only("id", "channel_id"):
        mapping_ids_by_channel.setdefault(mapping.channel_id, []).append(mapping.id)

    channel_by_id = {channel["id"]: channel for channel in channels}
    for plan in plan_account_associations(channels, runs, mapping_ids_by_channel):
        source = channel_by_id[plan["source_channel_ids"][0]]
        association = association_model.objects.create(
            name=plan["name"],
            integration_instance_id=plan["integration_instance_id"],
            platform_match_field=plan["platform_match_field"],
            external_match_field=plan["external_match_field"],
            external_receive_field=plan["external_receive_field"],
            schedule_config=plan["schedule_config"],
            status=plan["status"],
            created_by=source["created_by"],
            updated_by=source["updated_by"],
            domain=source["domain"],
            updated_by_domain=source["updated_by_domain"],
        )
        channel_model.objects.filter(id__in=plan["source_channel_ids"]).update(account_association_id=association.id)
        if plan["kept_mapping_ids"]:
            mapping_model.objects.filter(id__in=plan["kept_mapping_ids"]).update(account_association_id=association.id)
        mapping_model.objects.filter(channel_id__in=plan["source_channel_ids"]).exclude(id__in=plan["kept_mapping_ids"]).delete()
        if plan["run_ids"]:
            run_model.objects.filter(id__in=plan["run_ids"]).update(account_association_id=association.id)
        _close_extra_running_runs(run_model, association.id)

        next_status = "ready" if plan["status"] == "ready" else "needs_resync"
        channel_model.objects.filter(id__in=plan["source_channel_ids"]).exclude(status="disabled").update(status=next_status)

        for channel_id in plan["source_channel_ids"]:
            periodic_task_model.objects.filter(name=f"im_notification_channel_{channel_id}").delete()
        clock = _clock_parts(plan["schedule_config"].get("sync_time")) if plan["schedule_config"].get("enabled") else None
        if clock is not None:
            hour, minute = clock
            schedule, _ = crontab_model.objects.get_or_create(
                minute=str(int(minute)),
                hour=str(int(hour)),
                day_of_week="*",
                day_of_month="*",
                month_of_year="*",
                timezone=django.utils.timezone.get_current_timezone(),
            )
            periodic_task_model.objects.update_or_create(
                name=f"im_account_association_{association.id}",
                defaults={
                    "crontab": schedule,
                    "task": "apps.system_mgmt.tasks.schedule_im_account_association_sync",
                    "args": f"[{association.id}]",
                    "enabled": True,
                },
            )

    # PostgreSQL 把本次事务里新建的外键推迟到提交时检查。回填之后先做掉这些检查，
    # 后面的删字段和外键改必填才不会碰到尚未处理的约束触发器。
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.connection.check_constraints()


class Migration(migrations.Migration):
    dependencies = [
        ("system_mgmt", "0055_operationlog_idempotency_key"),
        ("django_celery_beat", "0018_improve_crontab_helptext"),
    ]

    operations = [
        migrations.CreateModel(
            name="IMAccountAssociation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                ("updated_by_domain", models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain")),
                ("name", models.CharField(max_length=100)),
                (
                    "platform_match_field",
                    models.CharField(
                        choices=[("username", "Platform Username"), ("email", "Platform Email"), ("phone", "Platform Mobile")],
                        default="email",
                        max_length=32,
                    ),
                ),
                ("external_match_field", models.CharField(default="email", max_length=64)),
                ("external_receive_field", models.CharField(default="user_id", max_length=64)),
                ("schedule_config", models.JSONField(blank=True, default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[("pending_sync", "Pending Sync"), ("ready", "Ready"), ("needs_resync", "Needs Resync")],
                        default="pending_sync",
                        max_length=32,
                    ),
                ),
                (
                    "integration_instance",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="account_associations",
                        to="system_mgmt.integrationinstance",
                    ),
                ),
            ],
            options={
                "ordering": ("name", "id"),
                "unique_together": {("name", "integration_instance")},
            },
        ),
        migrations.AddField(
            model_name="imnotificationchannel",
            name="account_association",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="notification_channels",
                to="system_mgmt.imaccountassociation",
            ),
        ),
        migrations.AddField(
            model_name="imnotificationusermapping",
            name="account_association",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="user_mappings",
                to="system_mgmt.imaccountassociation",
            ),
        ),
        migrations.AddField(
            model_name="imnotificationsyncrun",
            name="account_association",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="sync_runs",
                to="system_mgmt.imaccountassociation",
            ),
        ),
        migrations.RunPython(copy_account_associations, migrations.RunPython.noop),
        migrations.RemoveField(model_name="imnotificationchannel", name="platform_match_field"),
        migrations.RemoveField(model_name="imnotificationchannel", name="external_match_field"),
        migrations.RemoveField(model_name="imnotificationchannel", name="external_receive_field"),
        migrations.RemoveField(model_name="imnotificationchannel", name="schedule_config"),
        migrations.RemoveConstraint(
            model_name="imnotificationsyncrun",
            name="unique_running_im_notification_sync_run_per_channel",
        ),
        migrations.RemoveConstraint(
            model_name="imnotificationsyncrun",
            name="uniq_im_sync_run_guard_per_channel",
        ),
        migrations.AlterUniqueTogether(
            name="imnotificationusermapping",
            unique_together={("account_association", "user"), ("account_association", "external_identity_key", "external_identity_value")},
        ),
        migrations.RemoveField(model_name="imnotificationusermapping", name="channel"),
        migrations.RemoveField(model_name="imnotificationsyncrun", name="channel"),
        migrations.AlterField(
            model_name="imnotificationusermapping",
            name="account_association",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="user_mappings",
                to="system_mgmt.imaccountassociation",
            ),
        ),
        migrations.AlterField(
            model_name="imnotificationsyncrun",
            name="account_association",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="sync_runs",
                to="system_mgmt.imaccountassociation",
            ),
        ),
        migrations.AddConstraint(
            model_name="imnotificationsyncrun",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "running")),
                fields=("account_association",),
                name="unique_running_im_account_association_sync_run",
            ),
        ),
        migrations.AddConstraint(
            model_name="imnotificationsyncrun",
            constraint=models.UniqueConstraint(
                fields=("account_association", "running_guard"),
                name="uniq_im_sync_run_guard_per_account_association",
            ),
        ),
    ]
