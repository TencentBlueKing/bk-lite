from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("opspilot", "0076_alter_llmmodel_context_window_tokens"),
    ]

    operations = [
        migrations.AlterField(
            model_name="llmskill",
            name="show_think",
            field=models.BooleanField(default=False),
        ),
    ]
