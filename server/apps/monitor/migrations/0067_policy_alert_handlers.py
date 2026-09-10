from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0066_monitoralert_organizations"),
    ]

    operations = [
        migrations.AddField(
            model_name="monitorpolicy",
            name="handlers",
            field=models.JSONField(default=list, verbose_name="处理人"),
        ),
        migrations.AddField(
            model_name="monitoralert",
            name="handlers",
            field=models.JSONField(default=list, verbose_name="处理人"),
        ),
    ]
