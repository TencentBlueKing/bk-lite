from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("job_mgmt", "0021_jobexecution_client_request_id")]

    operations = [
        migrations.AddField(
            model_name="jobexecution",
            name="credential_actor",
            field=models.JSONField(blank=True, null=True, editable=False, verbose_name="执行凭据消费身份"),
        ),
    ]
