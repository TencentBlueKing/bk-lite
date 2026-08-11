from cryptography.fernet import InvalidToken
from django.db import migrations

from apps.core.mixinx import EncryptMixin


ENVELOPE_KEY = "__bklite_encrypted__"
ENVELOPE_VERSION = 1
BATCH_SIZE = 500


def _iter_bk_login_modules(login_module_model, database_alias):
    last_pk = 0
    while True:
        batch = list(
            login_module_model.objects.using(database_alias).filter(source_type="bk_login", pk__gt=last_pk)
            .order_by("pk")[:BATCH_SIZE]
        )
        if not batch:
            return
        yield from batch
        last_pk = batch[-1].pk


def _decrypt_compatible_app_token(value):
    if not value:
        return value

    if isinstance(value, dict):
        envelope = value.get(ENVELOPE_KEY)
        if not isinstance(envelope, dict) or envelope.get("version") != ENVELOPE_VERSION:
            raise RuntimeError("Invalid bk_login app_token envelope")
        encrypted_value = envelope.get("ciphertext")
        if not isinstance(encrypted_value, str) or not encrypted_value:
            raise RuntimeError("Invalid bk_login app_token envelope")
    elif isinstance(value, str):
        encrypted_value = value
    else:
        raise RuntimeError("bk_login app_token must be a string")

    try:
        return (
            EncryptMixin.get_cipher_suite()
            .decrypt(encrypted_value.encode(EncryptMixin.ENCODING))
            .decode(EncryptMixin.ENCODING)
        )
    except InvalidToken:
        if isinstance(value, str):
            return value
        raise RuntimeError("Failed to decrypt bk_login app_token during migration") from None
    except Exception as exc:
        raise RuntimeError("Failed to decrypt bk_login app_token during migration") from exc


def _encrypt_app_token(value):
    if isinstance(value, dict):
        _decrypt_compatible_app_token(value)
        return value

    plaintext = _decrypt_compatible_app_token(value)
    if not plaintext or not isinstance(plaintext, str):
        return plaintext

    config = {"app_token": plaintext}
    EncryptMixin.encrypt_field("app_token", config)
    if config["app_token"] == plaintext:
        raise RuntimeError("Failed to encrypt bk_login app_token during migration")
    return {
        ENVELOPE_KEY: {
            "version": ENVELOPE_VERSION,
            "ciphertext": config["app_token"],
        }
    }


def encrypt_existing_bk_login_app_tokens(apps, schema_editor):
    login_module_model = apps.get_model("system_mgmt", "LoginModule")
    database_alias = schema_editor.connection.alias if schema_editor else "default"
    for login_module in _iter_bk_login_modules(login_module_model, database_alias):
        config = dict(login_module.other_config or {})
        if not config.get("app_token"):
            continue

        config["app_token"] = _encrypt_app_token(config["app_token"])
        login_module_model.objects.using(database_alias).filter(pk=login_module.pk).update(other_config=config)


def decrypt_existing_bk_login_app_tokens(apps, schema_editor):
    login_module_model = apps.get_model("system_mgmt", "LoginModule")
    database_alias = schema_editor.connection.alias if schema_editor else "default"
    for login_module in _iter_bk_login_modules(login_module_model, database_alias):
        config = dict(login_module.other_config or {})
        if not config.get("app_token"):
            continue

        config["app_token"] = _decrypt_compatible_app_token(config["app_token"])
        login_module_model.objects.using(database_alias).filter(pk=login_module.pk).update(other_config=config)


class Migration(migrations.Migration):
    dependencies = [("system_mgmt", "0045_cross_database_running_guards")]

    operations = [
        migrations.RunPython(encrypt_existing_bk_login_app_tokens, decrypt_existing_bk_login_app_tokens),
    ]
