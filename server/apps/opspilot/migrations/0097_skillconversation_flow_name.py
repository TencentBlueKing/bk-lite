from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("opspilot", "0096_answer_feedback_tags")]

    operations = [
        migrations.AddField(
            model_name="skillconversation",
            name="flow_name",
            field=models.CharField(blank=True, default="", max_length=255, verbose_name="来源流程名称"),
        ),
    ]
