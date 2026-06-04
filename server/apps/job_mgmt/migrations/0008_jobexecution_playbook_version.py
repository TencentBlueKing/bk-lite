from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("job_mgmt", "0007_add_team_to_distributionfile"),
    ]

    operations = [
        migrations.AddField(
            model_name="jobexecution",
            name="playbook_version",
            field=models.CharField(blank=True, default="", max_length=32, verbose_name="执行时Playbook版本"),
        ),
    ]
