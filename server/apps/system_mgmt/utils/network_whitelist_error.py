NETWORK_WHITELIST_REQUIRED = "NETWORK_WHITELIST_REQUIRED"
NETWORK_WHITELIST_URL = "/system-manager/settings/network-whitelist"

DEFAULT_MESSAGE = "The target IP is not in the allowlist. Add it in System Management > Network Allowlist."
DEFAULT_ACTION_LABEL = "Open Network Allowlist"


def build_network_whitelist_error_payload(loader=None):
    """Build the shared API contract for allowlist-remediable outbound targets."""
    message = loader.get("error.network_whitelist_required", DEFAULT_MESSAGE) if loader else DEFAULT_MESSAGE
    action_label = loader.get("error.go_to_network_whitelist", DEFAULT_ACTION_LABEL) if loader else DEFAULT_ACTION_LABEL
    return {
        "result": False,
        "code": NETWORK_WHITELIST_REQUIRED,
        "message": message,
        "data": {
            "network_whitelist_url": NETWORK_WHITELIST_URL,
            "action_label": action_label,
        },
    }
