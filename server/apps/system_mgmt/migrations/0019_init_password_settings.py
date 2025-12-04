# Generated manually

from django.db import migrations


def create_password_settings(apps, schema_editor):
    """创建密码策略配置项"""
    SystemSettings = apps.get_model("system_mgmt", "SystemSettings")

    password_settings = [
        {"key": "pwd_set_min_length", "value": "8"},
        {"key": "pwd_set_max_length", "value": "20"},
        {"key": "pwd_set_required_char_types", "value": "uppercase,lowercase,digit,special"},
        {"key": "pwd_set_validity_period", "value": "180"},
        {"key": "pwd_set_max_retry_count", "value": "3"},
        {"key": "pwd_set_lock_duration", "value": "180"},
        {"key": "pwd_set_expiry_reminder_days", "value": "7"},
    ]

    # 批量创建配置项（如果不存在）
    for setting in password_settings:
        SystemSettings.objects.get_or_create(key=setting["key"], defaults={"value": setting["value"]})


class Migration(migrations.Migration):
    dependencies = [
        ("system_mgmt", "0018_errorlog"),
    ]

    operations = [
        migrations.RunPython(create_password_settings, migrations.RunPython.noop),
    ]
