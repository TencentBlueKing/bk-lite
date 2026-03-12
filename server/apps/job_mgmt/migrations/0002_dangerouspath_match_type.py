# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("job_mgmt", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="dangerouspath",
            name="match_type",
            field=models.CharField(
                choices=[("exact", "精确匹配"), ("regex", "正则匹配")],
                default="exact",
                max_length=32,
                verbose_name="匹配方式",
            ),
        ),
    ]
