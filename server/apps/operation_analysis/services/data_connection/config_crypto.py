from copy import deepcopy

from apps.core.utils.crypto.password_crypto import PasswordCrypto
from apps.operation_analysis.constants.constants import SECRET_KEY
from apps.operation_analysis.constants.import_export import SENSITIVE_PLACEHOLDER, is_sensitive_field_name

ENC_PREFIX = "enc$"


def _crypto():
    return PasswordCrypto(SECRET_KEY)


def encrypt_secret(value):
    if value in (None, "", SENSITIVE_PLACEHOLDER):
        return value
    if not isinstance(value, str):
        return value
    if value.startswith(ENC_PREFIX):
        return value
    return f"{ENC_PREFIX}{_crypto().encrypt(value)}"


def decrypt_secret(value):
    if value in (None, ""):
        return value
    if not isinstance(value, str) or not value.startswith(ENC_PREFIX):
        return value
    return _crypto().decrypt(value[len(ENC_PREFIX) :])


def encrypt_connection_config(config):
    return _transform_sensitive_config(config, encrypt_secret)


def decrypt_connection_config(config):
    return _transform_sensitive_config(config, decrypt_secret)


def _transform_sensitive_config(value, transformer):
    if isinstance(value, list):
        return [_transform_sensitive_config(item, transformer) for item in value]
    if not isinstance(value, dict):
        return value

    transformed = {}
    for key, item in value.items():
        if key == "headers" and isinstance(item, dict):
            transformed[key] = {
                header_key: transformer(header_value) if isinstance(header_value, str) else header_value
                for header_key, header_value in item.items()
            }
        elif is_sensitive_field_name(key) and isinstance(item, str):
            transformed[key] = transformer(item)
        else:
            transformed[key] = _transform_sensitive_config(item, transformer)
    return transformed


def redact_connection_config(config):
    from apps.operation_analysis.serializers.datasource_serializers import redact_sensitive_config

    return redact_sensitive_config(deepcopy(config) if isinstance(config, dict) else {})


def merge_connection_config(existing, incoming):
    from apps.operation_analysis.serializers.datasource_serializers import merge_redacted_config

    return merge_redacted_config(existing or {}, incoming or {})
