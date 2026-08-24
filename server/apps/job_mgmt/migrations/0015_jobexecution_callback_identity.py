from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("job_mgmt", "0014_jobcompletionoutbox")]

    operations = [
        migrations.AddField(
            model_name="jobexecution",
            name="callback_attempt_id",
            field=models.CharField(blank=True, default="", max_length=64, null=True, verbose_name="Ansible 回调执行 attempt ID"),
        ),
        migrations.AddField(
            model_name="jobexecution",
            name="callback_token_hash",
            field=models.CharField(blank=True, default="", max_length=64, null=True, verbose_name="Ansible 回调令牌摘要"),
        ),
    ]
