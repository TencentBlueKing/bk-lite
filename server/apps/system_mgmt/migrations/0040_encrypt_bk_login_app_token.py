from django.db import migrations

from apps.core.mixinx import EncryptMixin


def encrypt_existing_bk_login_app_tokens(apps, schema_editor):
    login_module_model = apps.get_model("system_mgmt", "LoginModule")
    for login_module in login_module_model.objects.filter(source_type="bk_login").iterator():
        config = dict(login_module.other_config or {})
        if not config.get("app_token"):
            continue

        EncryptMixin.decrypt_field("app_token", config)
        plaintext = config["app_token"]
        EncryptMixin.encrypt_field("app_token", config)
        if config["app_token"] == plaintext:
            raise RuntimeError(f"Failed to encrypt bk_login app_token for LoginModule {login_module.pk}")
        login_module_model.objects.filter(pk=login_module.pk).update(other_config=config)


def decrypt_existing_bk_login_app_tokens(apps, schema_editor):
    login_module_model = apps.get_model("system_mgmt", "LoginModule")
    for login_module in login_module_model.objects.filter(source_type="bk_login").iterator():
        config = dict(login_module.other_config or {})
        if not config.get("app_token"):
            continue

        EncryptMixin.decrypt_field("app_token", config)
        login_module_model.objects.filter(pk=login_module.pk).update(other_config=config)


class Migration(migrations.Migration):
    dependencies = [("system_mgmt", "0039_user_user_id")]

    operations = [
        migrations.RunPython(encrypt_existing_bk_login_app_tokens, decrypt_existing_bk_login_app_tokens),
    ]
