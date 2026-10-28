from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0063_processfingerprint"),
    ]

    operations = [
        migrations.AddField(
            model_name="scanhit",
            name="confidence",
            field=models.CharField(
                choices=[("low", "低"), ("medium", "中"), ("high", "高")],
                default="low",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="scanhit",
            name="evidence",
            field=models.JSONField(default=list, help_text="发现证据：port / process / collect"),
        ),
    ]
