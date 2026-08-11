"""TaskStore 对外查询与持久消息的敏感字段脱敏。"""

from copy import deepcopy
from typing import Any

SENSITIVE_CREDENTIAL_KEYS = {
    "password",
    "private_key_content",
    "private_key_passphrase",
    "ansible_password",
    "ansible_ssh_passphrase",
    "ansible_become_password",
    "inventory_content",
}

SENSITIVE_EXTRA_VAR_MARKERS = (
    "password",
    "passphrase",
    "private_key",
    "secret",
    "session_url",
    "token",
)


def _sanitize_extra_vars(extra_vars: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in extra_vars.items():
        if any(marker in str(key).lower() for marker in SENSITIVE_EXTRA_VAR_MARKERS):
            sanitized[key] = "***"
        else:
            sanitized[key] = _sanitize_extra_var_value(value)
    return sanitized


def _sanitize_extra_var_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _sanitize_extra_vars(value)
    if isinstance(value, list):
        return [_sanitize_extra_var_value(item) for item in value]
    return value


def _sanitize_callback_for_storage(callback: dict[str, Any] | None) -> dict[str, Any]:
    sanitized = dict(callback or {})
    context = sanitized.get("context")
    if isinstance(context, dict):
        sanitized["context"] = {**context, "token": "***"} if "token" in context else dict(context)
    return sanitized


def _sanitize_execution_payload_for_storage(payload: dict[str, Any]) -> dict[str, Any]:
    """保留执行凭据，但去掉已由独立密文列托管的 callback token 副本。"""
    sanitized = deepcopy(payload or {})
    if isinstance(sanitized.get("callback"), dict):
        sanitized["callback"] = _sanitize_callback_for_storage(sanitized["callback"])
    return sanitized


def _sanitize_payload_for_storage(payload: dict[str, Any]) -> dict[str, Any]:
    """移除查询态与持久消息不需要的凭据。"""
    if not payload:
        return payload

    sanitized = dict(payload)
    if isinstance(sanitized.get("host_credentials"), list):
        sanitized_creds = []
        for credential in sanitized["host_credentials"]:
            if not isinstance(credential, dict):
                continue
            safe_credential = {
                key: value
                for key, value in credential.items()
                if key not in SENSITIVE_CREDENTIAL_KEYS
            }
            safe_credential["_redacted"] = True
            sanitized_creds.append(safe_credential)
        sanitized["host_credentials"] = sanitized_creds

    for key in SENSITIVE_CREDENTIAL_KEYS:
        sanitized.pop(key, None)
    if isinstance(sanitized.get("extra_vars"), dict):
        sanitized["extra_vars"] = _sanitize_extra_vars(sanitized["extra_vars"])
    if isinstance(sanitized.get("callback"), dict):
        sanitized["callback"] = _sanitize_callback_for_storage(sanitized["callback"])
    return sanitized
