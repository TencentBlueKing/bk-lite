from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("opspilot", "0093_skill_history_analysis")]

    operations = [
        migrations.AddField(
            model_name="skillconversationmessage",
            name="feedback",
            field=models.CharField(blank=True, choices=[("like", "点赞"), ("dislike", "点踩")], max_length=7, null=True, verbose_name="回答评价"),
        ),
    ]
