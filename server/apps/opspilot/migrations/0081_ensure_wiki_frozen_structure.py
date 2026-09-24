from django.db import migrations


def apply_frozen_structure(apps, schema_editor):
    from apps.opspilot.services.wiki.frozen_structure_migration_service import ensure_all_frozen_structures

    ensure_all_frozen_structures(operator="system")


class Migration(migrations.Migration):
    dependencies = [
        ("opspilot", "0080_alter_skillchannel_channel_type"),
    ]

    operations = [
        migrations.RunPython(apply_frozen_structure, migrations.RunPython.noop),
    ]
