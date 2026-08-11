from django.db import migrations

from apps.core.mixinx import EncryptMixin


ENCRYPTION_PREFIX = "bklite:v1:"
BATCH_SIZE = 500


def _iter_bk_login_modules(login_module_model):
    last_pk = 0
    while True:
        batch = list(
            login_module_model.objects.filter(source_type="bk_login", pk__gt=last_pk)
            .order_by("pk")[:BATCH_SIZE]
        )
        if not batch:
            return
        yield from batch
        last_pk = batch[-1].pk


def _decrypt_versioned_app_token(value):
    if not value or not isinstance(value, str) or not value.startswith(ENCRYPTION_PREFIX):
        return value

    encrypted_value = value.removeprefix(ENCRYPTION_PREFIX)
    try:
        return EncryptMixin.get_cipher_suite().decrypt(encrypted_value.encode(EncryptMixin.ENCODING)).decode(EncryptMixin.ENCODING)
    except Exception as exc:
        raise RuntimeError("Failed to decrypt bk_login app_token during migration") from exc


def _encrypt_app_token(value):
    plaintext = _decrypt_versioned_app_token(value)
    if not plaintext or not isinstance(plaintext, str):
        return plaintext

    config = {"app_token": plaintext}
    EncryptMixin.encrypt_field("app_token", config)
    if config["app_token"] == plaintext:
        raise RuntimeError("Failed to encrypt bk_login app_token during migration")
    return f"{ENCRYPTION_PREFIX}{config['app_token']}"


def encrypt_existing_bk_login_app_tokens(apps, schema_editor):
    login_module_model = apps.get_model("system_mgmt", "LoginModule")
    for login_module in _iter_bk_login_modules(login_module_model):
        config = dict(login_module.other_config or {})
        if not config.get("app_token"):
            continue

        config["app_token"] = _encrypt_app_token(config["app_token"])
        login_module_model.objects.filter(pk=login_module.pk).update(other_config=config)


def decrypt_existing_bk_login_app_tokens(apps, schema_editor):
    login_module_model = apps.get_model("system_mgmt", "LoginModule")
    for login_module in _iter_bk_login_modules(login_module_model):
        config = dict(login_module.other_config or {})
        if not config.get("app_token"):
            continue

        config["app_token"] = _decrypt_versioned_app_token(config["app_token"])
        login_module_model.objects.filter(pk=login_module.pk).update(other_config=config)


class Migration(migrations.Migration):
    dependencies = [("system_mgmt", "0045_cross_database_running_guards")]

    operations = [
        migrations.RunPython(encrypt_existing_bk_login_app_tokens, decrypt_existing_bk_login_app_tokens),
    ]
