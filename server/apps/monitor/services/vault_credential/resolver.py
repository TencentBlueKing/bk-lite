"""Resolve and describe vault credentials for the current actor."""

from __future__ import annotations

from dataclasses import dataclass

from apps.rpc.system_mgmt import SystemMgmt
from apps.system_mgmt.services.credential_builtin import BUILTIN_TYPES, builtin_fields_for_key
from apps.system_mgmt.services.credential_schema import SchemaError, validate_instance_fields

from .errors import VaultCredentialError, map_describe_message, map_resolve_message


@dataclass
class ResolvedCredential:
    credential_id: str
    type_key: str
    name: str
    version: int
    fields: dict
    disabled: bool = False


def describe_for_actor(actor_context, credential_id, variant):
    _require_actor(actor_context)
    payload = SystemMgmt().describe_credential(_actor_payload(actor_context), credential_id)
    data = _payload_data(payload, map_describe_message)
    _require_type(data.get("type"), variant)
    return ResolvedCredential(
        credential_id=str(data.get("credential_id") or credential_id),
        type_key=str(data.get("type") or ""),
        name=str(data.get("name") or ""),
        version=int(data.get("secret_version") or 0),
        fields={},
        disabled=bool(data.get("disabled")),
    )


def resolve_for_actor(actor_context, credential_id, variant, *, form_values=None):
    _require_actor(actor_context)
    payload = SystemMgmt().resolve_credential(_actor_payload(actor_context), credential_id)
    data = _payload_data(payload, map_resolve_message)
    type_key = str(data.get("type") or "")
    _require_type(type_key, variant)
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    _require_complete(type_key, fields)
    _require_snmp_version(variant, fields, form_values or {})
    try:
        version = int(data.get("secret_version") or 0)
    except (TypeError, ValueError) as exc:
        raise VaultCredentialError("apply_failed") from exc
    return ResolvedCredential(
        credential_id=str(data.get("credential_id") or credential_id),
        type_key=type_key,
        name=str(data.get("name") or ""),
        version=version,
        fields=fields,
        disabled=False,
    )


def _require_actor(actor_context):
    actor = actor_context or {}
    if not actor.get("username") or not actor.get("domain") or actor.get("current_team") in (None, ""):
        raise VaultCredentialError("forbidden")


def _actor_payload(actor_context):
    return {
        "username": actor_context.get("username"),
        "domain": actor_context.get("domain"),
        "current_team": actor_context.get("current_team"),
    }


def _payload_data(payload, mapper):
    if not isinstance(payload, dict) or payload.get("result") is False:
        message = payload.get("message") if isinstance(payload, dict) else ""
        raise VaultCredentialError(mapper(message))
    data = payload.get("data")
    if not isinstance(data, dict):
        raise VaultCredentialError("apply_failed")
    return data


def _require_type(type_key, variant):
    allowed = list((variant or {}).get("type_keys") or [])
    if type_key not in allowed:
        raise VaultCredentialError("type_mismatch")


def _require_complete(type_key, fields):
    type_fields = builtin_fields_for_key(type_key)
    if type_fields is None:
        preferred = _preferred_for_actual(type_key)
        type_fields = builtin_fields_for_key(preferred) if preferred else None
    if not type_fields:
        definition = BUILTIN_TYPES.get(type_key)
        type_fields = list((definition or {}).get("fields") or [])
    try:
        validate_instance_fields(type_fields=type_fields, values=fields, require_secrets=True)
    except SchemaError as exc:
        raise VaultCredentialError("incomplete") from exc


def _preferred_for_actual(type_key):
    from apps.system_mgmt.services.credential_builtin import BUILTIN_KEY_FALLBACKS

    for preferred, fallback in BUILTIN_KEY_FALLBACKS.items():
        if fallback == type_key:
            return preferred
    return None


def _require_snmp_version(variant, fields, form_values):
    if (variant or {}).get("_profile") not in {"snmp_v2", "snmp_v3"} and not (variant or {}).get("snmp_version_field"):
        return
    if not (variant or {}).get("snmp_version_field"):
        return
    form_version = form_values.get("version", (variant or {}).get("key"))
    try:
        form_version = int(form_version)
    except (TypeError, ValueError):
        form_version = form_values.get("version")
    credential_version = str(fields.get("version") or "")
    if form_version == 2 and credential_version in {"v2", "v2c"}:
        return
    if form_version == 3 and credential_version == "v3":
        return
    raise VaultCredentialError("version_mismatch")
