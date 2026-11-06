from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("opspilot", "0086_skill_asset_tags"),
    ]

    operations = [
        migrations.AddField(
            model_name="llmskill",
            name="allow_wiki_material_write",
            field=models.BooleanField(default=False, verbose_name="允许通过对话修改知识库"),
        ),
    ]
