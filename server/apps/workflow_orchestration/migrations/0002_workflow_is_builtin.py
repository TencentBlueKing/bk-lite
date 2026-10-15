from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workflow_orchestration", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="workflow",
            name="is_builtin",
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]
