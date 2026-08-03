import uuid

import django.db.models.deletion
from django.db import migrations, models


def migrate_legacy_notification_configuration(apps, schema_editor):
    Policy = apps.get_model("apm", "ApmPolicy")
    Target = apps.get_model("apm", "ApmPolicyNotificationTarget")
    Outbox = apps.get_model("apm", "ApmAlertOutbox")

    for policy in Policy.objects.filter(notice=True).iterator():
        recipients = policy.notice_users if isinstance(policy.notice_users, list) else []
        channel_ids = policy.notice_type_ids if isinstance(policy.notice_type_ids, list) else []
        normalized_ids = set()
        for channel_id in channel_ids:
            try:
                normalized_ids.add(int(channel_id))
            except (TypeError, ValueError):
                continue
        for channel_id in sorted(normalized_ids):
            Target.objects.get_or_create(
                policy=policy,
                channel_id=channel_id,
                defaults={
                    "delivery_mode": "alert_event_copy",
                    "recipient_mode": "none",
                    "recipients": recipients,
                },
            )

    for outbox in Outbox.objects.order_by("created_at", "id").iterator():
        payload = outbox.payload if isinstance(outbox.payload, dict) else {}
        outbox.recipients = outbox.receivers if isinstance(outbox.receivers, list) else []
        outbox.delivery_mode = "alert_event_copy"
        outbox.title = str(payload.get("title") or "")[:512]
        outbox.body = str(payload.get("description") or payload.get("title") or "")[:20_000]
        if outbox.delivery_status == "delivered":
            outbox.delivered_at = outbox.updated_at
        outbox.save(
            update_fields=(
                "recipients",
                "delivery_mode",
                "title",
                "body",
                "delivered_at",
                "updated_at",
            )
        )


def restore_legacy_notification_configuration(apps, schema_editor):
    Policy = apps.get_model("apm", "ApmPolicy")
    for policy in Policy.objects.prefetch_related("notification_targets").iterator():
        targets = list(policy.notification_targets.order_by("channel_id", "id"))
        recipients = []
        for target in targets:
            for recipient in target.recipients if isinstance(target.recipients, list) else []:
                if recipient not in recipients:
                    recipients.append(recipient)
        policy.notice = bool(targets)
        policy.notice_type_ids = [target.channel_id for target in targets]
        policy.notice_users = recipients
        policy.save(update_fields=("notice", "notice_type_ids", "notice_users", "updated_at"))


class Migration(migrations.Migration):
    dependencies = [("apm", "0003_apm_owned_alert_lifecycle")]

    operations = [
        migrations.CreateModel(
            name="ApmPolicyNotificationTarget",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                ("updated_by_domain", models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain")),
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("channel_id", models.PositiveBigIntegerField(db_index=True)),
                ("channel_name", models.CharField(blank=True, default="", max_length=100)),
                ("channel_type", models.CharField(blank=True, default="", max_length=30)),
                ("delivery_mode", models.CharField(choices=[("message", "普通通知"), ("alert_event_copy", "告警中心事件副本")], max_length=32)),
                ("recipient_mode", models.CharField(choices=[("none", "无需接收人"), ("system_user", "系统用户"), ("free_text", "自由输入")], max_length=32)),
                ("recipients", models.JSONField(default=list)),
                ("policy", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notification_targets", to="apm.apmpolicy")),
            ],
            options={
                "verbose_name": "APM 策略通知目标",
                "verbose_name_plural": "APM 策略通知目标",
                "ordering": ("channel_id", "id"),
            },
        ),
        migrations.AddConstraint(
            model_name="apmpolicynotificationtarget",
            constraint=models.UniqueConstraint(fields=("policy", "channel_id"), name="apm_policy_notification_target_unique"),
        ),
        migrations.AddField(model_name="apmalertoutbox", name="recipients", field=models.JSONField(default=list)),
        migrations.AddField(model_name="apmalertoutbox", name="channel_name", field=models.CharField(blank=True, default="", max_length=100)),
        migrations.AddField(model_name="apmalertoutbox", name="channel_type", field=models.CharField(blank=True, default="", max_length=30)),
        migrations.AddField(model_name="apmalertoutbox", name="delivery_mode", field=models.CharField(blank=True, default="message", max_length=32)),
        migrations.AddField(model_name="apmalertoutbox", name="title", field=models.CharField(blank=True, default="", max_length=512)),
        migrations.AddField(model_name="apmalertoutbox", name="body", field=models.TextField(blank=True, default="")),
        migrations.AddField(model_name="apmalertoutbox", name="claimed_at", field=models.DateTimeField(blank=True, db_index=True, null=True)),
        migrations.AddField(model_name="apmalertoutbox", name="last_error_code", field=models.CharField(blank=True, default="", max_length=128)),
        migrations.AddField(model_name="apmalertoutbox", name="last_error_message", field=models.CharField(blank=True, default="", max_length=512)),
        migrations.AddField(model_name="apmalertoutbox", name="delivered_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="apmalertoutbox", name="failed_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AlterField(
            model_name="apmalertoutbox",
            name="delivery_status",
            field=models.CharField(choices=[("pending", "待投递"), ("delivered", "已投递"), ("failed", "终止失败")], db_index=True, default="pending", max_length=16),
        ),
        migrations.CreateModel(
            name="ApmNotificationDeliveryRetry",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("created_by", models.CharField(default="", max_length=32, verbose_name="Creator")),
                ("updated_by", models.CharField(default="", max_length=32, verbose_name="Updater")),
                ("domain", models.CharField(default="domain.com", max_length=100, verbose_name="Domain")),
                ("updated_by_domain", models.CharField(default="domain.com", max_length=100, verbose_name="updated by domain")),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("requested_by", models.CharField(max_length=150)),
                ("previous_attempts", models.PositiveIntegerField(default=0)),
                ("previous_error_code", models.CharField(blank=True, default="", max_length=128)),
                ("previous_error_message", models.CharField(blank=True, default="", max_length=512)),
                ("delivery", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="manual_retries", to="apm.apmalertoutbox")),
            ],
            options={
                "verbose_name": "APM 通知人工重投审计",
                "verbose_name_plural": "APM 通知人工重投审计",
                "ordering": ("-created_at", "-id"),
            },
        ),
        migrations.RunPython(migrate_legacy_notification_configuration, restore_legacy_notification_configuration),
    ]
