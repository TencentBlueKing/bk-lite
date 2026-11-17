from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("opspilot", "0089_skillconversation_workbench")]

    operations = [
        migrations.AddField(
            model_name="skillconversationmessage",
            name="organization_id",
            field=models.IntegerField(blank=True, null=True, verbose_name="对话时的组织ID"),
        ),
    ]
