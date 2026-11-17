import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("opspilot", "0088_material_chat_sourced")]

    operations = [
        migrations.AlterField(
            model_name="skillconversation",
            name="channel",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="conversations",
                to="opspilot.skillchannel",
                verbose_name="渠道绑定",
            ),
        ),
    ]
