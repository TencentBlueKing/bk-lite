"""Unit tests for Anthropic OpenAI-compat vision client."""

from types import SimpleNamespace

import pytest

from apps.opspilot.services.wiki.parsing import anthropic_vision_compat as compat


def test_openai_messages_to_anthropic_converts_data_uri_image():
    png_b64 = "aGVsbG8="  # "hello"
    system, messages = compat.openai_messages_to_anthropic(
        [
            {"role": "system", "content": "be brief"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "describe"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{png_b64}"},
                    },
                ],
            },
        ]
    )

    assert system == "be brief"
    assert messages == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "describe"},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": png_b64,
                    },
                },
            ],
        }
    ]


def test_openai_messages_to_anthropic_keeps_http_image_url():
    _, messages = compat.openai_messages_to_anthropic(
        [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": "https://example.com/a.png"},
                    }
                ],
            }
        ]
    )

    assert messages[0]["content"] == [
        {
            "type": "image",
            "source": {"type": "url", "url": "https://example.com/a.png"},
        }
    ]


def test_openai_image_part_rejects_unsupported_scheme():
    with pytest.raises(ValueError, match="unsupported image_url scheme"):
        compat._openai_image_part_to_anthropic({"type": "image_url", "image_url": {"url": "file:///tmp/a.png"}})


def test_compat_client_create_maps_to_anthropic_messages():
    captured = {}

    class FakeAnthropic:
        class messages:
            @staticmethod
            def create(**kwargs):
                captured.update(kwargs)
                return SimpleNamespace(content=[SimpleNamespace(type="text", text="一页摘要")])

    client = compat.AnthropicOpenAICompatClient(FakeAnthropic())
    resp = client.chat.completions.create(
        model="claude-sonnet",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "概括第 1 页"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,aGVsbG8="},
                    },
                ],
            }
        ],
        max_tokens=200,
    )

    assert resp.choices[0].message.content == "一页摘要"
    assert captured["model"] == "claude-sonnet"
    assert captured["max_tokens"] == 200
    assert captured["messages"][0]["role"] == "user"
    assert captured["messages"][0]["content"][1]["type"] == "image"


def test_build_anthropic_vision_client_normalizes_empty_base(monkeypatch):
    created = {}

    class FakeAnthropic:
        def __init__(self, api_key, base_url):
            created.update(api_key=api_key, base_url=base_url)

    monkeypatch.setattr(compat.anthropic, "Anthropic", FakeAnthropic)

    client = compat.build_anthropic_vision_client(
        api_base="",
        api_key="sk-ant",
        vendor_type="anthropic",
    )

    assert isinstance(client, compat.AnthropicOpenAICompatClient)
    assert created == {
        "api_key": "sk-ant",
        "base_url": "https://api.anthropic.com",
    }


def test_describe_page_with_vision_works_via_anthropic_compat():
    from apps.opspilot.services.wiki.parsing.pdf_hybrid_parser import describe_page_with_vision

    class FakeAnthropic:
        class messages:
            @staticmethod
            def create(**kwargs):
                return SimpleNamespace(content=[SimpleNamespace(type="text", text="目录页")])

    client = compat.AnthropicOpenAICompatClient(FakeAnthropic())
    assert describe_page_with_vision(client, "claude-sonnet", b"\x89PNG", 3) == "目录页"
