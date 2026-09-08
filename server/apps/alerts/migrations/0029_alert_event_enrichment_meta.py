from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("alerts", "0028_enrichmentrule_preset_key"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="enrichment_meta",
            field=models.JSONField(default=dict, help_text="丰富执行诊断（有界状态摘要）"),
        ),
        migrations.AddField(
            model_name="alert",
            name="enrichment_meta",
            field=models.JSONField(default=dict, help_text="成员事件丰富执行聚合摘要"),
        ),
    ]
