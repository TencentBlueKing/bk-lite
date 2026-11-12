from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("itsm", "0008_aisetting_announcement_bizobject_changewindow_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="ticketstatus",
            name="description",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
    ]
