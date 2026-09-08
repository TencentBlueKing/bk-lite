from copy import deepcopy

from apps.core.mixinx import EncryptMixin
from apps.system_mgmt.services.credential_schema import secret_field_ids


def encrypt_instance_fields(type_fields, new_values, old_encrypted=None) -> dict:
    """Encrypt secret fields while retaining stored values for blank updates."""
    old_values = old_encrypted or {}
    values = deepcopy(old_values)
    values.update(deepcopy(new_values or {}))

    incoming = new_values or {}
    for field_id in secret_field_ids(type_fields):
        if field_id not in incoming:
            continue
        if incoming[field_id] in (None, ""):
            if field_id in old_values:
                values[field_id] = old_values[field_id]
        else:
            EncryptMixin.encrypt_field(field_id, values)

    return values


def decrypt_instance_fields(type_fields, encrypted_values) -> dict:
    """Decrypt secret fields for server-only credential resolution."""
    values = deepcopy(encrypted_values or {})
    for field_id in secret_field_ids(type_fields):
        EncryptMixin.decrypt_field(field_id, values)
    return values


def public_instance_fields(type_fields, encrypted_values) -> dict:
    """Return instance fields without exposing secret values."""
    values = deepcopy(encrypted_values or {})
    for field_id in secret_field_ids(type_fields):
        values.pop(field_id, None)
    return values
