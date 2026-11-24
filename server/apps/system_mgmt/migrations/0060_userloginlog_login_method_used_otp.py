from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("system_mgmt", "0059_operationlog_outcome_target_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="userloginlog",
            name="login_method",
            field=models.CharField(blank=True, default="", max_length=64, verbose_name="Login Method"),
        ),
        migrations.AddField(
            model_name="userloginlog",
            name="used_otp",
            field=models.BooleanField(default=False, verbose_name="Used OTP"),
        ),
    ]
