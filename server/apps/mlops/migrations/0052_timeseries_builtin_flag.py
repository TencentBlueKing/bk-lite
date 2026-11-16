from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("mlops", "0051_externalresourcecleanupintent_resource_types"),
    ]

    operations = [
        migrations.AddField(
            model_name="timeseriespredicttrainjob",
            name="is_builtin",
            field=models.BooleanField(default=False, verbose_name="内置记录"),
        ),
        migrations.AddField(
            model_name="timeseriespredictserving",
            name="is_builtin",
            field=models.BooleanField(default=False, verbose_name="内置记录"),
        ),
    ]
