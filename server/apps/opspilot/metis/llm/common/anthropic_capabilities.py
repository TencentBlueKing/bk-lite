from dataclasses import dataclass


@dataclass(frozen=True)
class AnthropicRuntimeCapabilities:
    use_native_anthropic_sdk: bool = False
    use_anthropic_compatible_adapter: bool = False
    thinking_requires_auto_tool_choice: bool = False
    supports_direct_messages_api: bool = False
    requires_normalized_base_url: bool = False


def build_anthropic_runtime_capabilities(
    vendor_type: str,
    protocol_type: str,
) -> AnthropicRuntimeCapabilities:
    if protocol_type != "anthropic":
        return AnthropicRuntimeCapabilities()

    if not vendor_type:
        return AnthropicRuntimeCapabilities(
            use_native_anthropic_sdk=True,
        )

    if vendor_type == "anthropic":
        return AnthropicRuntimeCapabilities(
            use_native_anthropic_sdk=True,
        )

    if vendor_type == "deepseek":
        return AnthropicRuntimeCapabilities(
            use_anthropic_compatible_adapter=True,
            thinking_requires_auto_tool_choice=True,
            supports_direct_messages_api=True,
            requires_normalized_base_url=True,
        )

    return AnthropicRuntimeCapabilities(
        use_anthropic_compatible_adapter=True,
        supports_direct_messages_api=True,
        requires_normalized_base_url=True,
    )


def normalize_tool_choice_for_capabilities(
    tool_choice: str,
    capabilities: AnthropicRuntimeCapabilities,
) -> str:
    if capabilities.thinking_requires_auto_tool_choice and tool_choice in {"any", "required"}:
        return "auto"
    return tool_choice
