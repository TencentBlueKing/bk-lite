"""
Anthropic Compatible Adapter

Shared helpers for validating connectivity to Anthropic-protocol endpoints
(native Anthropic API and Anthropic-compatible providers such as DeepSeek).
"""

from apps.core.utils.safe_requests import safe_post_llm_endpoint

_ANTHROPIC_DEFAULT_BASE = "https://api.anthropic.com"
_ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_INVALID_API_KEY_ERROR = "API Key 无效"


def normalize_messages_url(api_base: str) -> str:
    """Return the /v1/messages URL for the given api_base.

    Defaults to the official Anthropic base when api_base is empty.
    """
    base = (api_base or _ANTHROPIC_DEFAULT_BASE).rstrip("/")
    return f"{base}/v1/messages"


def build_anthropic_headers(api_key: str) -> dict:
    """Build the HTTP headers required by the Anthropic messages API."""
    return {
        "x-api-key": api_key,
        "anthropic-version": _ANTHROPIC_VERSION,
        "content-type": "application/json",
    }


class AnthropicCompatibleAdapter:
    """Adapter for Anthropic-protocol endpoints (native and compatible)."""

    @staticmethod
    def validate_minimal_connection(api_base: str, api_key: str, model: str) -> None:
        """POST a minimal request to verify the endpoint is reachable.

        Raises:
            ValueError: if the API key is invalid or the request fails.
        """
        url = normalize_messages_url(api_base)
        headers = build_anthropic_headers(api_key)
        response = safe_post_llm_endpoint(
            url,
            headers=headers,
            json={
                "model": model,
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "hi"}],
            },
            timeout=15,
        )
        AnthropicCompatibleAdapter._raise_for_error(response)

    @staticmethod
    def _raise_for_error(response) -> None:
        """Raise ValueError for non-2xx responses."""
        if response.status_code == 401:
            raise ValueError(ANTHROPIC_INVALID_API_KEY_ERROR)
        if response.status_code >= 400:
            error_msg = response.text[:200] if response.text else f"HTTP {response.status_code}"
            raise ValueError(f"API 连接失败: {error_msg}")
