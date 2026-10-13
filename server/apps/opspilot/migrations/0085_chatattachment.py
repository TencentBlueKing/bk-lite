import django.db.models.deletion
import django_minio_backend.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("opspilot", "0084_llmskill_run_model_call_limit"),
    ]

    operations = [
        migrations.CreateModel(
            name="ChatAttachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "file",
                    models.FileField(
                        storage=django_minio_backend.models.MinioBackend(bucket_name="munchkin-private"),
                        upload_to=django_minio_backend.models.iso_date_prefix,
                        verbose_name="附件文件",
                    ),
                ),
                ("original_name", models.CharField(max_length=255, verbose_name="原始文件名")),
                ("mime_type", models.CharField(max_length=120, verbose_name="MIME")),
                ("size", models.PositiveIntegerField(verbose_name="字节大小")),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "解析中"), ("ready", "就绪"), ("failed", "失败")],
                        db_index=True,
                        default="pending",
                        max_length=16,
                        verbose_name="状态",
                    ),
                ),
                ("parsed_text", models.TextField(blank=True, default="", verbose_name="解析文本")),
                ("failure_reason", models.CharField(blank=True, default="", max_length=255, verbose_name="失败原因")),
                ("owner_key", models.CharField(db_index=True, max_length=255, verbose_name="上传者")),
                ("team_id", models.CharField(db_index=True, max_length=64, verbose_name="组织")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="创建时间")),
                (
                    "conversation",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chat_attachments",
                        to="opspilot.skillconversation",
                        verbose_name="会话",
                    ),
                ),
                (
                    "message",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="chat_attachments",
                        to="opspilot.skillconversationmessage",
                        verbose_name="消息",
                    ),
                ),
            ],
            options={
                "verbose_name": "对话附件",
                "verbose_name_plural": "对话附件",
                "db_table": "model_provider_mgmt_chatattachment",
                "indexes": [
                    models.Index(fields=["status", "created_at"], name="chat_att_status_created_idx"),
                    models.Index(fields=["message", "status"], name="chat_att_message_status_idx"),
                ],
            },
        ),
    ]
