from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operation_analysis", "0040_screen_display_grant"),
    ]

    operations = [
        migrations.AddField(
            model_name="datasourceapimodel",
            name="portable_key",
            field=models.CharField(blank=True, max_length=64, null=True, unique=True, verbose_name="可移植身份"),
        ),
    ]
