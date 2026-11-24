import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("itsm", "0021_trigger_execution_history")]

    operations = [
        migrations.AddField(
            model_name="knowledgearticle",
            name="category",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="knowledgearticle",
            name="content_format",
            field=models.CharField(
                choices=[("text", "纯文本"), ("richtext", "富文本"), ("markdown", "Markdown")],
                default="text",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="knowledgearticle",
            name="tickets",
            field=models.ManyToManyField(blank=True, related_name="knowledge_articles", to="itsm.ticket"),
        ),
        migrations.CreateModel(
            name="KnowledgeAttachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("size", models.PositiveIntegerField()),
                ("object_name", models.CharField(max_length=100, unique=True)),
                (
                    "article",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attachments",
                        to="itsm.knowledgearticle",
                    ),
                ),
            ],
            options={"db_table": "itsm_knowledge_attachment"},
        ),
    ]
