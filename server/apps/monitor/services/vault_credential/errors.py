"""Stable credential error codes for monitor vault access."""

from __future__ import annotations

ALLOWED_CODES = frozenset(
    {
        "forbidden",
        "disabled",
        "not_found",
        "team_archived",
        "type_mismatch",
        "incomplete",
        "version_mismatch",
        "username_invalid",
        "inline_secret_required",
        "credential_required",
        "managed_key_in_instances",
        "apply_failed",
    }
)

DESCRIBE_MESSAGES = frozenset({"forbidden", "disabled", "not_found", "team_archived", "invalid"})
RESOLVE_MESSAGES = frozenset({"forbidden", "disabled", "not_found", "invalid"})
CLEARED_SYNC_ERRORS = frozenset({"disabled", "not_found", "forbidden"})


class VaultCredentialError(Exception):
    """Credential failure. The message is only the stable code."""

    def __init__(self, code: str):
        if code not in ALLOWED_CODES:
            raise ValueError("invalid vault credential code")
        self.code = code
        super().__init__(code)


def client_code(code: str) -> str:
    if code not in ALLOWED_CODES:
        raise ValueError("invalid vault credential code")
    return f"credential_{code}"


def map_describe_message(message) -> str:
    text = str(message or "")
    if text in {"forbidden", "not_found", "team_archived"}:
        return text
    if text == "disabled":
        return "disabled"
    return "apply_failed"


def map_resolve_message(message) -> str:
    text = str(message or "")
    if text in {"forbidden", "disabled", "not_found"}:
        return text
    return "apply_failed"
