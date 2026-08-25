from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


def normalize_invalid_timeouts(apps, schema_editor):
    collect_model = apps.get_model("cmdb", "CollectModels")
    collect_model.objects.filter(timeout__lt=1).update(timeout=60)


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0049_scan_models"),
    ]

    operations = [
        migrations.RunPython(normalize_invalid_timeouts, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="collectmodels",
            name="timeout",
            field=models.PositiveIntegerField(
                default=60,
                help_text="单目标采集总预算(秒)",
                validators=[MinValueValidator(1), MaxValueValidator(86400)],
            ),
        ),
    ]
