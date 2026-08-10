import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("opspilot", "0068_wikiknowledgebase_directory_migration_state"),
    ]

    operations = [
        migrations.AlterField(
            model_name="llmskill",
            name="llm_model",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="opspilot.llmmodel",
                verbose_name="LLM模型",
            ),
        ),
    ]
