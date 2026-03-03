"""
Data migration to upgrade Celery schedule configuration format.

Converts old format (time as single string):
    {
        "frequency": "daily",
        "time": "00:00",
        "message": "xxx",
        ...
    }

To new format (time as list):
    {
        "frequency": "daily",
        "time": ["00:00"],
        "message": "xxx",
        ...
    }
"""

from django.db import migrations


def upgrade_schedule_config(apps, schema_editor):
    """
    Upgrade old config format (time as string) to new format (time as list).
    """
    BotWorkFlow = apps.get_model("opspilot", "BotWorkFlow")

    for workflow in BotWorkFlow.objects.all():
        if not workflow.web_json:
            continue

        nodes = workflow.web_json.get("nodes", [])
        if not nodes:
            continue

        modified = False
        for node in nodes:
            if node.get("type") != "celery":
                continue

            data = node.get("data", {})
            config = data.get("config", {})

            # Skip if time field doesn't exist
            if "time" not in config:
                continue

            time_value = config.get("time")

            # Skip if already new format (time is a list)
            if isinstance(time_value, list):
                continue

            # Convert old format: time string -> time list
            if isinstance(time_value, str):
                config["time"] = [time_value]
                modified = True

        if modified:
            workflow.save(update_fields=["web_json"])


def downgrade_schedule_config(apps, schema_editor):
    """
    Downgrade new config format (time as list) back to old format (time as string).

    Note: Only the first time in the list will be preserved.
    """
    BotWorkFlow = apps.get_model("opspilot", "BotWorkFlow")

    for workflow in BotWorkFlow.objects.all():
        if not workflow.web_json:
            continue

        nodes = workflow.web_json.get("nodes", [])
        if not nodes:
            continue

        modified = False
        for node in nodes:
            if node.get("type") != "celery":
                continue

            data = node.get("data", {})
            config = data.get("config", {})

            # Skip if time field doesn't exist
            if "time" not in config:
                continue

            time_value = config.get("time")

            # Skip if already old format (time is a string)
            if isinstance(time_value, str):
                continue

            # Convert new format: time list -> time string (first item only)
            if isinstance(time_value, list) and len(time_value) > 0:
                config["time"] = time_value[0]
                modified = True

        if modified:
            workflow.save(update_fields=["web_json"])


class Migration(migrations.Migration):
    dependencies = [
        ("opspilot", "0041_bot_is_pinned"),
    ]

    operations = [
        migrations.RunPython(
            upgrade_schedule_config,
            reverse_code=downgrade_schedule_config,
        ),
    ]
