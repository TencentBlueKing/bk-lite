# Generated manually

import os

from django.db import migrations


def create_builtin_nats_channel(apps, schema_editor):
    """创建内置的告警中心 NATS Channel"""
    Channel = apps.get_model("system_mgmt", "Channel")

    namespace = os.getenv("NATS_NAMESPACE", "bk_lite")

    Channel.objects.get_or_create(
        name="告警中心",
        channel_type="nats",
        defaults={
            "config": {
                "namespace": namespace,
                "method_name": "receive_alert_events",
                "timeout": 60,
            },
            "description": "内置告警中心通道，用于接收告警事件",
            "team": [1],
        },
    )


def reverse_create(apps, schema_editor):
    """删除内置的告警中心 NATS Channel"""
    Channel = apps.get_model("system_mgmt", "Channel")
    Channel.objects.filter(name="告警中心", channel_type="nats").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("system_mgmt", "0023_update_channel_team_default"),
    ]

    operations = [
        migrations.RunPython(create_builtin_nats_channel, reverse_create),
    ]
