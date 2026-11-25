from django.db import migrations, models

LEGACY_REASONS = ("inaccurate", "incomplete", "off_topic", "hard_to_use")


def convert_single_reasons(apps, schema_editor):
    messages = apps.get_model("opspilot", "SkillConversationMessage").objects.using(schema_editor.connection.alias)
    for reason in LEGACY_REASONS:
        messages.filter(feedback_reason=reason).update(feedback_reasons=[reason])


def restore_single_reasons(apps, schema_editor):
    messages = apps.get_model("opspilot", "SkillConversationMessage").objects.using(schema_editor.connection.alias)
    for message in messages.filter(feedback="dislike").exclude(feedback_reasons=[]).only("feedback_reasons").iterator():
        reason = next((tag for tag in message.feedback_reasons if tag in LEGACY_REASONS), "")
        if reason:
            messages.filter(pk=message.pk).update(feedback_reason=reason)


class Migration(migrations.Migration):
    dependencies = [("opspilot", "0095_answer_feedback_reason")]
    operations = [
        migrations.AddField(
            model_name="skillconversationmessage",
            name="feedback_reasons",
            field=models.JSONField(blank=True, default=list, verbose_name="评价标签"),
        ),
        migrations.RunPython(convert_single_reasons, restore_single_reasons),
        migrations.RemoveField(model_name="skillconversationmessage", name="feedback_reason"),
        migrations.AlterField(
            model_name="skillconversationmessage",
            name="feedback_comment",
            field=models.CharField(blank=True, default="", max_length=500, verbose_name="评价说明"),
        ),
    ]
