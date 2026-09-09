from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("apm", "0016_apm_policy_organization"),
    ]

    operations = [
        migrations.AddField(
            model_name="apmpolicy",
            name="handlers",
            field=models.JSONField(default=list),
        ),
        migrations.AddField(
            model_name="apmalert",
            name="handlers",
            field=models.JSONField(default=list),
        ),
    ]
