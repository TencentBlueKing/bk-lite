from typing import Any

from .schemas import ProviderManifest


class ProviderRegistry:
    def __init__(self):
        self._providers: dict[str, ProviderManifest] = {}

    def clear(self):
        self._providers.clear()

    def register(self, manifest: ProviderManifest):
        if manifest.key in self._providers:
            raise ValueError(f"Provider '{manifest.key}' is already registered")
        self._providers[manifest.key] = manifest

    def get(self, provider_key: str) -> ProviderManifest | None:
        return self._providers.get(provider_key)

    def list(self) -> list[ProviderManifest]:
        return list(self._providers.values())


class CapabilityAdapterRegistry:
    def __init__(self):
        self._adapters: dict[str, type[Any]] = {}

    def clear(self):
        self._adapters.clear()

    def register(self, adapter_key: str, adapter_cls: type[Any]):
        if adapter_key in self._adapters:
            raise ValueError(f"Adapter '{adapter_key}' is already registered")
        self._adapters[adapter_key] = adapter_cls

    def get(self, adapter_key: str) -> type[Any] | None:
        return self._adapters.get(adapter_key)


provider_registry = ProviderRegistry()
capability_adapter_registry = CapabilityAdapterRegistry()


def get_provider_registry() -> ProviderRegistry:
    return provider_registry


def get_capability_adapter_registry() -> CapabilityAdapterRegistry:
    return capability_adapter_registry
