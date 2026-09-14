from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("opspilot", "0077_alter_llmskill_show_think"),
    ]

    operations = [
        migrations.AddField(
            model_name="llmskill",
            name="force_wiki_grounded",
            field=models.BooleanField(default=False, verbose_name="强制知识库回答"),
        ),
    ]
