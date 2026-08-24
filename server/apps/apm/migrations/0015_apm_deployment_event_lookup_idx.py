from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("apm", "0014_apm_deployment_event"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="apmdeploymentevent",
            index=models.Index(fields=["service", "environment", "-deployed_at"], name="apm_deploy_svc_env_time_idx"),
        ),
    ]
