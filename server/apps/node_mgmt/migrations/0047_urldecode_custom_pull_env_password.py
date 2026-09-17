from urllib.parse import unquote

from django.db import migrations, transaction

from apps.core.logger import node_logger as logger
from apps.core.utils.crypto.aes_crypto import AESCryptor

BATCH_SIZE = 100
CUSTOM_PULL_TYPES = frozenset({"custom_pull", "bkpull"})
PASSWORD_KEY_NAMES = ("PASSWORD",)


def _key_matches(key, names) -> bool:
    upper = str(key or "").upper()
    return upper in names or any(upper.startswith(f"{name}__") for name in names)


def is_custom_pull_password_env_key(key, collect_type="", config_type="") -> bool:
    """PASSWORD used as Telegraf prometheus Basic Auth, not URL-embedded."""
    if not _key_matches(key, PASSWORD_KEY_NAMES):
        return False
    return str(collect_type or "") in CUSTOM_PULL_TYPES or str(config_type or "") in CUSTOM_PULL_TYPES


def urldecode_custom_pull_password_env_config(env_config, cryptor, collect_type="", config_type=""):
    """Decrypt custom_pull/bkpull PASSWORD secrets, undo encodeURIComponent, re-encrypt."""
    if not isinstance(env_config, dict) or not env_config:
        return env_config, 0

    rewritten = 0
    updated = dict(env_config)
    for key, value in env_config.items():
        if not is_custom_pull_password_env_key(key, collect_type, config_type) or not value:
            continue
        try:
            plaintext = cryptor.decode(str(value))
        except Exception as error:
            logger.debug(
                "event=custom_pull_password_urldecode_skip key=%s failed_stage=aes_decode error_type=%s",
                key,
                type(error).__name__,
            )
            continue
        decoded = unquote(plaintext)
        if decoded == plaintext:
            continue
        updated[key] = cryptor.encode(decoded)
        rewritten += 1
    return updated, rewritten


def urldecode_custom_pull_passwords(apps, schema_editor):
    """Decrypt → URL-decode → re-encrypt PASSWORD keys on custom_pull/bkpull child configs.

    Only ChildConfig rows whose collect_type or config_type is custom_pull/bkpull.
    host / postgres / mongodb / mssql / mysql / ipmi PASSWORD keys stay URL-encoded.
    BEARER_TOKEN is unchanged (already skipped / migrated in 0046).
    """
    database_alias = schema_editor.connection.alias
    cryptor = AESCryptor()
    child_config = apps.get_model("node_mgmt", "ChildConfig")

    scanned = 0
    rewritten_rows = 0
    rewritten_fields = 0
    last_pk = ""
    while True:
        with transaction.atomic(using=database_alias):
            rows = list(child_config.objects.using(database_alias).select_for_update().filter(pk__gt=last_pk).order_by("pk")[:BATCH_SIZE])
            if not rows:
                break
            for row in rows:
                scanned += 1
                updated, rewritten = urldecode_custom_pull_password_env_config(
                    row.env_config,
                    cryptor,
                    collect_type=row.collect_type,
                    config_type=row.config_type,
                )
                if rewritten:
                    row.env_config = updated
                    row.save(update_fields=["env_config"], using=database_alias)
                    rewritten_rows += 1
                    rewritten_fields += rewritten
            last_pk = rows[-1].pk

    logger.info(
        "event=custom_pull_password_urldecode_completed child_scanned=%s child_rows=%s child_fields=%s",
        scanned,
        rewritten_rows,
        rewritten_fields,
    )


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("node_mgmt", "0046_urldecode_snmp_v3_env_secrets"),
    ]

    operations = [
        migrations.RunPython(urldecode_custom_pull_passwords, migrations.RunPython.noop),
    ]
