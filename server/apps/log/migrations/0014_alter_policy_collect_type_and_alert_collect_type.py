from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("log", "0013_collecttype_display_category"),
    ]

    operations = [
        migrations.AlterField(
            model_name="alert",
            name="collect_type",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="log.collecttype",
                verbose_name="采集方式",
            ),
        ),
        migrations.AlterField(
            model_name="policy",
            name="collect_type",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="log.collecttype",
                verbose_name="采集方式",
            ),
        ),
    ]
