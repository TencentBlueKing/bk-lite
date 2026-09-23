from django.db import migrations, models
from django.utils.translation import gettext_lazy as _


class Migration(migrations.Migration):
    dependencies = [
        ("opspilot", "0079_skillchannel_public_id"),
    ]

    operations = [
        migrations.AlterField(
            model_name="skillchannel",
            name="channel_type",
            field=models.CharField(
                choices=[
                    ("platform", _("Platform")),
                    ("web_chat", _("Web Chat")),
                    ("embedded_chat", _("Embedded Chat")),
                    ("enterprise_wechat", _("Enterprise WeChat")),
                    ("enterprise_wechat_aibot", _("Enterprise WeChat AI Bot")),
                    ("dingtalk", _("Ding Talk")),
                    ("feishu", _("Feishu")),
                    ("wechat_official", _("WeChat Official Account")),
                ],
                db_index=True,
                max_length=64,
                verbose_name=_("channel type"),
            ),
        ),
    ]
