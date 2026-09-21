import uuid

from django.db import migrations, models


def fill_skillchannel_public_id(apps, schema_editor):
    SkillChannel = apps.get_model("opspilot", "SkillChannel")
    for channel in SkillChannel.objects.filter(public_id__isnull=True).iterator(chunk_size=200):
        channel.public_id = uuid.uuid4()
        channel.save(update_fields=["public_id"])


class Migration(migrations.Migration):
    dependencies = [
        ("opspilot", "0078_force_wiki_and_skill_memory"),
    ]

    operations = [
        migrations.AddField(
            model_name="skillchannel",
            name="public_id",
            field=models.UUIDField(blank=True, null=True, verbose_name="对外标识"),
        ),
        migrations.RunPython(fill_skillchannel_public_id, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="skillchannel",
            name="public_id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name="对外标识"),
        ),
    ]
