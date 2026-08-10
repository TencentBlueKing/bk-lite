import django.utils.timezone
import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("cmdb", "0037_cmdb_unique_write_lock")]

    operations = [
        migrations.CreateModel(
            name="ChangeRecordMirrorOutbox",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created Time")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated Time")),
                ("event_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("payloads", models.JSONField(default=list)),
                ("status", models.CharField(choices=[("pending", "等待投递"), ("sending", "投递中"), ("retry", "等待重试"), ("success", "成功"), ("failed", "失败")], default="pending", max_length=16)),
                ("owner_token", models.CharField(blank=True, default="", max_length=64)),
                ("lease_expires_at", models.DateTimeField(blank=True, null=True)),
                ("attempt_count", models.PositiveIntegerField(default=0)),
                ("last_error", models.TextField(blank=True, default="")),
                ("next_attempt_at", models.DateTimeField(default=django.utils.timezone.now)),
            ],
            options={"db_table": "cmdb_change_record_mirror_outbox"},
        ),
        migrations.AddIndex(
            model_name="changerecordmirroroutbox",
            index=models.Index(fields=["status", "next_attempt_at"], name="cmdb_cr_mirror_ready_idx"),
        ),
    ]
