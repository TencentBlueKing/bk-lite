from django.db import migrations, models


def create_sensitive_info_settings(apps, schema_editor):
    SystemSettings = apps.get_model("system_mgmt", "SystemSettings")

    settings = [
        {"key": "sensitive_info_protection_enabled", "value": "0"},
        {"key": "sensitive_info_types", "value": "email,phone"},
    ]

    for setting in settings:
        SystemSettings.objects.get_or_create(key=setting["key"], defaults={"value": setting["value"]})


class Migration(migrations.Migration):

    dependencies = [
        ('system_mgmt', '0030_user_phone'),
    ]

    operations = [
        migrations.CreateModel(
            name='SensitiveInfoAuthorization',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Created Time')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated Time')),
                ('created_by', models.CharField(default='', max_length=32, verbose_name='Creator')),
                ('updated_by', models.CharField(default='', max_length=32, verbose_name='Updater')),
                ('domain', models.CharField(default='domain.com', max_length=100, verbose_name='Domain')),
                ('updated_by_domain', models.CharField(default='domain.com', max_length=100, verbose_name='updated by domain')),
                ('username', models.CharField(max_length=100)),
                ('sensitive_types', models.JSONField(blank=True, default=list)),
                ('remark', models.CharField(blank=True, default='', max_length=255)),
            ],
            options={
                'indexes': [models.Index(fields=['username', 'domain'], name='system_mgmt_sensiauth_user_dom')],
                'unique_together': {('username', 'domain')},
            },
        ),
        migrations.RunPython(create_sensitive_info_settings, migrations.RunPython.noop),
    ]
