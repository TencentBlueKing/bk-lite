import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("system_mgmt", "0056_im_account_association"),
    ]

    operations = [
        migrations.AddField(
            model_name="channel",
            name="account_association",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="group_channels",
                to="system_mgmt.imaccountassociation",
            ),
        ),
    ]
