from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cmdb", "0075_owner_handover"),
    ]

    operations = [
        migrations.AddField(
            model_name="ownerhandovertask",
            name="attr_id",
            field=models.CharField(default="", max_length=128),
        ),
        migrations.AddField(
            model_name="ownerhandovertask",
            name="attr_name",
            field=models.CharField(default="", max_length=255),
        ),
    ]
