from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("opspilot", "0046_model_vendor_data_cleanup"),
    ]

    operations = [
        migrations.AddField(
            model_name="workflowtaskresult",
            name="finished_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="完成时间"),
        ),
    ]
