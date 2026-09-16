from urllib.parse import unquote

from django.db import migrations, transaction

from apps.core.logger import node_logger as logger
from apps.core.utils.crypto.aes_crypto import AESCryptor

BATCH_SIZE = 100
SNMP_V3_SECRET_KEYS = ("AUTH_PASSWORD", "PRIV_PASSWORD")
PLAINTEXT_HTTP_PASSWORD_CONFIG_TYPES = frozenset({"qcloud", "windows_wmi", "cisco_meraki", "web", "aliyun", "cnware"})
PLAINTEXT_HTTP_PASSWORD_COLLECT_TYPES = frozenset({"web"})


def _key_matches(key, names) -> bool:
    upper = str(key or "").upper()
    return upper in names or any(upper.startswith(f"{name}__") for name in names)


def is_snmp_v3_secret_env_key(key) -> bool:
    """Match AUTH_PASSWORD / PRIV_PASSWORD and sidecar suffixes AUTH_PASSWORD__<config_id>."""
    return _key_matches(key, SNMP_V3_SECRET_KEYS)


def is_plaintext_http_secret_env_key(key, collect_type="", config_type="") -> bool:
    """PASSWORD/BEARER used as HTTP headers or dedicated Telegraf fields, not URL-embedded."""
    if _key_matches(key, ("BEARER_TOKEN",)):
        return True
    if not _key_matches(key, ("PASSWORD",)):
        return False
    return str(collect_type or "") in PLAINTEXT_HTTP_PASSWORD_COLLECT_TYPES or str(config_type or "") in PLAINTEXT_HTTP_PASSWORD_CONFIG_TYPES


def should_urldecode_plaintext_secret_key(key, collect_type="", config_type="") -> bool:
    return is_snmp_v3_secret_env_key(key) or is_plaintext_http_secret_env_key(key, collect_type, config_type)


def urldecode_plaintext_secret_env_config(env_config, cryptor, collect_type="", config_type=""):
    """Decrypt plaintext-consumer secrets, undo encodeURIComponent, re-encrypt."""
    if not isinstance(env_config, dict) or not env_config:
        return env_config, 0

    rewritten = 0
    updated = dict(env_config)
    for key, value in env_config.items():
        if not should_urldecode_plaintext_secret_key(key, collect_type, config_type) or not value:
            continue
        try:
            plaintext = cryptor.decode(str(value))
        except Exception as error:
            logger.debug(
                "event=plaintext_secret_urldecode_skip key=%s failed_stage=aes_decode error_type=%s",
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


def _rewrite_model_env_configs(model, database_alias, cryptor, *, use_plugin_types=False):
    scanned = 0
    rewritten_rows = 0
    rewritten_fields = 0
    last_pk = ""
    while True:
        with transaction.atomic(using=database_alias):
            rows = list(model.objects.using(database_alias).select_for_update().filter(pk__gt=last_pk).order_by("pk")[:BATCH_SIZE])
            if not rows:
                break
            for row in rows:
                scanned += 1
                collect_type = row.collect_type if use_plugin_types else ""
                config_type = row.config_type if use_plugin_types else ""
                updated, rewritten = urldecode_plaintext_secret_env_config(
                    row.env_config,
                    cryptor,
                    collect_type=collect_type,
                    config_type=config_type,
                )
                if rewritten:
                    row.env_config = updated
                    row.save(update_fields=["env_config"], using=database_alias)
                    rewritten_rows += 1
                    rewritten_fields += rewritten
            last_pk = rows[-1].pk
    return scanned, rewritten_rows, rewritten_fields


def urldecode_stored_plaintext_secrets(apps, schema_editor):
    """Decrypt → URL-decode → re-encrypt plaintext-consumer env secrets.

    SNMPv3 AUTH/PRIV always. HTTP header / dedicated password fields only for
    web / qcloud / windows_wmi / cisco_meraki / aliyun / cnware. host /
    postgres / mongodb PASSWORD keys stay URL-encoded.
    """
    database_alias = schema_editor.connection.alias
    cryptor = AESCryptor()
    child_config = apps.get_model("node_mgmt", "ChildConfig")
    collector_configuration = apps.get_model("node_mgmt", "CollectorConfiguration")

    child_scanned, child_rows, child_fields = _rewrite_model_env_configs(child_config, database_alias, cryptor, use_plugin_types=True)
    parent_scanned, parent_rows, parent_fields = _rewrite_model_env_configs(collector_configuration, database_alias, cryptor, use_plugin_types=False)
    logger.info(
        "event=plaintext_secret_urldecode_completed child_scanned=%s child_rows=%s "
        "child_fields=%s parent_scanned=%s parent_rows=%s parent_fields=%s",
        child_scanned,
        child_rows,
        child_fields,
        parent_scanned,
        parent_rows,
        parent_fields,
    )


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("node_mgmt", "0045_collector_release_import_fields"),
    ]

    operations = [
        migrations.RunPython(urldecode_stored_plaintext_secrets, migrations.RunPython.noop),
    ]
