# Generated manually for skill+channel_type+name uniqueness.

from django.db import migrations, models


def dedupe_skill_channel_names(apps, schema_editor):
    """为即将加的唯一约束消解存量重复：同 skill/type/name 的后续记录改名为 name-id。"""
    SkillChannel = apps.get_model("opspilot", "SkillChannel")
    seen = {}
    to_update = []
    for ch in SkillChannel.objects.order_by("id").iterator():
        key = (ch.skill_id, ch.channel_type, ch.name or "")
        if key in seen:
            ch.name = f"{ch.name or ch.channel_type}-{ch.id}"
            to_update.append(ch)
        else:
            seen[key] = ch.id
    if to_update:
        SkillChannel.objects.bulk_update(to_update, ["name"], batch_size=500)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("opspilot", "0072_skill_usage_team_and_channels"),
    ]

    operations = [
        migrations.RunPython(dedupe_skill_channel_names, noop_reverse),
        migrations.AddConstraint(
            model_name="skillchannel",
            constraint=models.UniqueConstraint(
                fields=("skill", "channel_type", "name"),
                name="uniq_skillchannel_skill_type_name",
            ),
        ),
    ]
