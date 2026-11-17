import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("opspilot", "0090_skillconversationmessage_organization_id"),
        ("system_mgmt", "0056_im_account_association"),
    ]

    operations = [
        migrations.AddField(
            model_name="skillchannel",
            name="account_association",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="skill_channels",
                to="system_mgmt.imaccountassociation",
                verbose_name="账号关联",
            ),
        ),
    ]
