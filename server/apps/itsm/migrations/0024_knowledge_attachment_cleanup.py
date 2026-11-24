from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("itsm", "0023_trigger_notice_delivery")]

    operations = [
        migrations.CreateModel(
            name="KnowledgeAttachmentCleanup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("object_name", models.CharField(max_length=100, unique=True)),
                ("next_attempt_at", models.DateTimeField(db_index=True)),
            ],
            options={"db_table": "itsm_knowledge_attachment_cleanup"},
        ),
    ]
