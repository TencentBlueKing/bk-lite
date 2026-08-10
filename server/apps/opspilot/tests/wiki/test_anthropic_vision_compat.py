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


def test_openai_content_to_anthropic_handles_scalars_and_mixed_parts():
    assert compat.openai_content_to_anthropic(None) == ""
    assert compat.openai_content_to_anthropic("plain") == "plain"
    assert compat.openai_content_to_anthropic(12) == "12"
    assert compat.openai_content_to_anthropic(["hello", {"type": "text", "text": " world "}]) == [
        {"type": "text", "text": "hello"},
        {"type": "text", "text": "world"},
    ]


def test_openai_image_part_accepts_string_image_url_and_rejects_empty():
    block = compat._openai_image_part_to_anthropic({"type": "image_url", "image_url": "https://cdn.example/x.png"})
    assert block["source"]["url"] == "https://cdn.example/x.png"
    with pytest.raises(ValueError, match="empty image_url"):
        compat._openai_image_part_to_anthropic({"type": "image_url", "image_url": {"url": "  "}})


def test_openai_messages_to_anthropic_collects_system_text_blocks():
    system, messages = compat.openai_messages_to_anthropic(
        [
            {
                "role": "system",
                "content": [{"type": "text", "text": "sys-a"}, {"type": "text", "text": "sys-b"}],
            },
            {"role": "assistant", "content": "answer"},
            "ignore-me",
        ]
    )
    assert system == "sys-a\n\nsys-b"
    assert messages == [{"role": "assistant", "content": "answer"}]


def test_extract_text_supports_dict_and_string_content():
    assert compat._extract_text({"content": " hi "}) == "hi"
    assert compat._extract_text({"content": [{"type": "text", "text": "A"}, {"type": "text", "text": "B"}]}) == "AB"


def test_compat_client_requires_user_or_assistant_message():
    client = compat.AnthropicOpenAICompatClient(SimpleNamespace())
    with pytest.raises(ValueError, match="at least one user/assistant message"):
        client.chat.completions.create(model="claude", messages=[{"role": "system", "content": "only"}])


def test_build_anthropic_vision_client_rewrites_openai_default_base(monkeypatch):
    created = {}

    class FakeAnthropic:
        def __init__(self, api_key, base_url):
            created.update(api_key=api_key, base_url=base_url)

    monkeypatch.setattr(compat.anthropic, "Anthropic", FakeAnthropic)
    compat.build_anthropic_vision_client(
        api_base="https://api.openai.com",
        api_key="k",
        vendor_type="anthropic",
    )
    assert created["base_url"] == "https://api.anthropic.com"
