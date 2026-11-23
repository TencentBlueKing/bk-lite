from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("opspilot", "0091_skillchannel_account_association")]

    operations = [
        migrations.AddField(
            model_name="modelvendor",
            name="skip_ssl_verify",
            field=models.BooleanField(default=False, verbose_name="跳过 SSL 证书校验"),
        ),
    ]
