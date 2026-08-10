"""OpenAI-shaped vision client backed by Anthropic Messages API.

MarkItDown and Wiki PDF page description both call
``client.chat.completions.create`` with multimodal OpenAI content parts.
This adapter translates those calls to Anthropic ``messages.create``.
"""

from __future__ import annotations

import base64
import re
from types import SimpleNamespace
from urllib.parse import urlparse

import anthropic

from apps.opspilot.metis.llm.common.anthropic_compatible_adapter import normalize_anthropic_compatible_api_base

_DATA_URI_RE = re.compile(r"^data:([^;]+);base64,(.+)$", re.DOTALL | re.IGNORECASE)
_DEFAULT_MAX_TOKENS = 1024
_DEFAULT_ANTHROPIC_BASE = "https://api.anthropic.com"


def build_anthropic_vision_client(*, api_base: str, api_key: str, vendor_type: str = ""):
    """Return an OpenAI-compatible client for Anthropic-protocol vision models."""
    base = (api_base or "").strip()
    if not base or base == "https://api.openai.com":
        base = _DEFAULT_ANTHROPIC_BASE
    else:
        base = normalize_anthropic_compatible_api_base(base, vendor_type)
    return AnthropicOpenAICompatClient(
        anthropic.Anthropic(api_key=api_key or "", base_url=base),
    )


def _openai_image_part_to_anthropic(part: dict) -> dict:
    image = part.get("image_url") or {}
    url = ""
    if isinstance(image, dict):
        url = image.get("url") or ""
    elif isinstance(image, str):
        url = image
    url = (url or "").strip()
    if not url:
        raise ValueError("empty image_url")

    match = _DATA_URI_RE.match(url)
    if match:
        media_type = (match.group(1) or "image/png").strip().lower()
        data = match.group(2).strip()
        # Anthropic 要求纯 base64；解码一次做粗校验
        base64.b64decode(data)
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": data,
            },
        }

    parsed = urlparse(url)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return {
            "type": "image",
            "source": {
                "type": "url",
                "url": url,
            },
        }
    raise ValueError(f"unsupported image_url scheme: {parsed.scheme or 'empty'}")


def openai_content_to_anthropic(content) -> list[dict] | str:
    """Convert OpenAI chat content (str or multimodal parts) to Anthropic content."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)

    blocks: list[dict] = []
    for part in content:
        if isinstance(part, str):
            text = part.strip()
            if text:
                blocks.append({"type": "text", "text": text})
            continue
        if not isinstance(part, dict):
            continue
        part_type = part.get("type")
        if part_type == "text":
            text = (part.get("text") or "").strip()
            if text:
                blocks.append({"type": "text", "text": text})
        elif part_type == "image_url":
            blocks.append(_openai_image_part_to_anthropic(part))
    return blocks


def openai_messages_to_anthropic(messages: list) -> tuple[str | None, list[dict]]:
    """Split OpenAI chat messages into Anthropic (system, messages)."""
    system_parts: list[str] = []
    anthropic_messages: list[dict] = []
    for message in messages or []:
        if not isinstance(message, dict):
            continue
        role = message.get("role") or "user"
        content = openai_content_to_anthropic(message.get("content"))
        if role == "system":
            if isinstance(content, str) and content.strip():
                system_parts.append(content.strip())
            elif isinstance(content, list):
                for block in content:
                    if block.get("type") == "text" and block.get("text"):
                        system_parts.append(block["text"])
            continue
        mapped_role = "assistant" if role == "assistant" else "user"
        anthropic_messages.append({"role": mapped_role, "content": content or ""})
    system = "\n\n".join(system_parts) if system_parts else None
    return system, anthropic_messages


def _extract_text(response) -> str:
    content = getattr(response, "content", None)
    if content is None and isinstance(response, dict):
        content = response.get("content")
    if isinstance(content, str):
        return content.strip()
    parts: list[str] = []
    for block in content or []:
        if isinstance(block, dict):
            if block.get("type") == "text" and block.get("text"):
                parts.append(block["text"])
            continue
        if getattr(block, "type", None) == "text":
            text = getattr(block, "text", "") or ""
            if text:
                parts.append(text)
    return "".join(parts).strip()


class AnthropicOpenAICompatClient:
    """Minimal OpenAI client surface: ``chat.completions.create``."""

    def __init__(self, anthropic_client):
        self._client = anthropic_client
        self.chat = SimpleNamespace(completions=_Completions(anthropic_client))


class _Completions:
    def __init__(self, anthropic_client):
        self._client = anthropic_client

    def create(self, *, model, messages, max_tokens=None, **_kwargs):
        system, anthropic_messages = openai_messages_to_anthropic(messages)
        if not anthropic_messages:
            raise ValueError("anthropic vision requires at least one user/assistant message")
        call_kwargs = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": int(max_tokens or _DEFAULT_MAX_TOKENS),
        }
        if system:
            call_kwargs["system"] = system
        response = self._client.messages.create(**call_kwargs)
        text = _extract_text(response)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        )
