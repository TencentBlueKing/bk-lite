from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("apm", "0011_merge_apm_product_branches")]

    operations = [
        migrations.AddField(
            model_name="apmpolicy",
            name="no_data_alert_name",
            field=models.CharField(blank=True, default="", max_length=512),
        ),
    ]
