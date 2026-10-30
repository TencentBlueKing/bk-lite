"""全目录用户字段的保存规则。"""

import re

from apps.system_mgmt.models.user_field import UserFieldDefinition, UserFieldType, UserFieldValue
from apps.system_mgmt.services.user_profile import PROFILE_KEYS, field_mapping_targets

KEY_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


class UserFieldError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def _clean_key(raw):
    key = str(raw or "").strip()
    if not KEY_PATTERN.match(key) or key in PROFILE_KEYS or key.casefold() in {item.casefold() for item in PROFILE_KEYS}:
        raise UserFieldError("invalid field key")
    return key


def _clean_type(raw):
    field_type = str(raw or "").strip()
    if field_type not in UserFieldType.values:
        raise UserFieldError("invalid field type")
    return field_type


def serialize_definition(definition):
    return {
        "id": definition.id,
        "name": definition.name,
        "key": definition.key,
        "field_type": definition.field_type,
        "description": definition.description,
        "is_enabled": definition.is_enabled,
        "has_values": UserFieldValue.objects.filter(field=definition).exists(),
        "mapped": bool(field_mapping_targets(definition.key)),
    }


def create_definition(*, name, key, field_type, description=""):
    cleaned_name = str(name or "").strip()
    if not cleaned_name:
        raise UserFieldError("field name required")
    cleaned_key = _clean_key(key)
    if UserFieldDefinition.objects.filter(key=cleaned_key).exists():
        raise UserFieldError("field key exists")
    return UserFieldDefinition.objects.create(
        name=cleaned_name[:64],
        key=cleaned_key,
        field_type=_clean_type(field_type),
        description=str(description or ""),
    )


def update_definition(definition, *, name, description, field_type=None, key=None):
    if key is not None and str(key).strip() != definition.key:
        raise UserFieldError("field key immutable")
    cleaned_name = str(name or "").strip()
    if not cleaned_name:
        raise UserFieldError("field name required")
    if field_type is not None and _clean_type(field_type) != definition.field_type:
        if UserFieldValue.objects.filter(field=definition).exists() or field_mapping_targets(definition.key):
            raise UserFieldError("field type locked")
        definition.field_type = _clean_type(field_type)
    definition.name = cleaned_name[:64]
    definition.description = str(description or "")
    definition.save()
    return definition


def disable_definition(definition):
    if field_mapping_targets(definition.key):
        raise UserFieldError("field still mapped")
    definition.is_enabled = False
    definition.save(update_fields=["is_enabled", "updated_at"])
    return definition


def enable_definition(definition):
    definition.is_enabled = True
    definition.save(update_fields=["is_enabled", "updated_at"])
    return definition


def delete_definition(definition):
    if UserFieldValue.objects.filter(field=definition).exists() or field_mapping_targets(definition.key):
        raise UserFieldError("field cannot be deleted")
    definition.delete()
