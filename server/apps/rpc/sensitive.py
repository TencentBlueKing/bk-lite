"""Sensitive payload masking for RPC observable surfaces."""

from __future__ import annotations

import re
from typing import Any

MASKED_VALUE = "***"

_DIRECT_MASK_KEYS = {
    "password",
    "passphrase",
    "private_key",
    "private_key_content",
    "private_key_passphrase",
    "inventory_content",
    "ansible_password",
    "ansible_ssh_passphrase",
    "ansible_become_password",
}
_RECURSE_ONLY_KEYS = {"host_credentials"}

_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?P<key>"
    r"password|passphrase|private_key|private_key_content|private_key_passphrase|inventory_content|"
    r"ansible_password|ansible_ssh_passphrase|ansible_become_password"
    r")(?P<sep>\s*[:=]\s*)(?P<value>'[^']*'|\"[^\"]*\"|[^,\s}\]]+)",
    re.IGNORECASE,
)
_PRIVATE_KEY_BLOCK_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.DOTALL,
)


def _mask_match(match: re.Match[str]) -> str:
    value = match.group("value")
    if value.startswith(("'", '"')) and value.endswith(value[0]):
        masked = f"{value[0]}{MASKED_VALUE}{value[0]}"
    else:
        masked = MASKED_VALUE
    return f"{match.group('key')}{match.group('sep')}{masked}"


def _sanitize_string(value: str) -> str:
    if not value:
        return value
    masked = _PRIVATE_KEY_BLOCK_RE.sub(MASKED_VALUE, value)
    return _SENSITIVE_ASSIGNMENT_RE.sub(_mask_match, masked)


def sanitize_sensitive_data(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).lower()
            if normalized_key in _DIRECT_MASK_KEYS:
                sanitized[key] = MASKED_VALUE if item not in (None, "") else item
            elif normalized_key in _RECURSE_ONLY_KEYS:
                sanitized[key] = sanitize_sensitive_data(item)
            else:
                sanitized[key] = sanitize_sensitive_data(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_sensitive_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_sensitive_data(item) for item in value)
    if isinstance(value, str):
        return _sanitize_string(value)
    return value


def summarize_ansible_callback(data: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "task_id": data.get("task_id"),
        "task_type": data.get("task_type"),
        "status": data.get("status"),
        "success": data.get("success"),
        "started_at": data.get("started_at"),
        "finished_at": data.get("finished_at"),
    }
    error = data.get("error")
    if error:
        summary["error"] = sanitize_sensitive_data(error)

    result = data.get("result")
    if isinstance(result, list):
        summary["result_count"] = len(result)
        summary["hosts"] = [
            {
                "host": item.get("host"),
                "status": item.get("status"),
                "exit_code": item.get("exit_code"),
                "output_truncated": item.get("output_truncated"),
            }
            for item in result
            if isinstance(item, dict)
        ]
    else:
        summary["result_type"] = type(result).__name__
    return summary
