from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("opspilot", "0061_buildrecord_checkitem_knowledgepage_material_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="material",
            name="sync_policy",
            field=models.JSONField(default=dict),
        ),
    ]
