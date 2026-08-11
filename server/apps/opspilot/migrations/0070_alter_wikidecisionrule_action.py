from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("opspilot", "0069_alter_llmskill_llm_model"),
    ]

    operations = [
        migrations.AlterField(
            model_name="wikidecisionrule",
            name="action",
            field=models.CharField(
                choices=[
                    ("keep_current", "保留当前知识"),
                    ("keep_all", "全部保留"),
                    ("use_new", "使用新知识"),
                    ("edit_accept", "编辑后采用"),
                    ("keep_separate", "保持页面独立"),
                    ("merge", "确认页面合并"),
                ],
                max_length=40,
            ),
        ),
    ]
