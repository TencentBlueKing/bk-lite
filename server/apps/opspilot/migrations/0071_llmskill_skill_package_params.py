from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("opspilot", "0070_alter_wikidecisionrule_action"),
    ]

    operations = [
        migrations.AddField(
            model_name="llmskill",
            name="skill_package_params",
            field=models.JSONField(default=dict, verbose_name="技能包参数"),
        ),
    ]
