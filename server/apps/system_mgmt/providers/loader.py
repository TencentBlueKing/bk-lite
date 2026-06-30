from importlib import import_module

from django.utils.module_loading import import_string

from apps.core.logger import logger

from .registry import get_capability_adapter_registry, get_provider_registry
from .schemas import ProviderManifest

BUILTIN_PROVIDER_MODULES = (
    "apps.system_mgmt.providers.manifests.feishu",
    "apps.system_mgmt.providers.manifests.wechat",
    "apps.system_mgmt.providers.manifests.ad",
)

_providers_loaded = False


def load_builtin_providers(force: bool = False):
    global _providers_loaded

    if _providers_loaded and not force:
        return

    provider_registry = get_provider_registry()
    adapter_registry = get_capability_adapter_registry()
    provider_registry.clear()
    adapter_registry.clear()

    for module_path in BUILTIN_PROVIDER_MODULES:
        module = import_module(module_path)
        raw_manifest = getattr(module, "PROVIDER_MANIFEST", None)
        if raw_manifest is None:
            raise ValueError(f"Provider module '{module_path}' does not expose PROVIDER_MANIFEST")

        manifest = raw_manifest if isinstance(raw_manifest, ProviderManifest) else ProviderManifest.model_validate(raw_manifest)
        provider_registry.register(manifest)

        for capability in manifest.capabilities:
            adapter_cls = import_string(capability.adapter_path)
            adapter_registry.register(capability.adapter_key, adapter_cls)

        logger.info(f"Loaded provider manifest '{manifest.key}' with {len(manifest.capabilities)} capabilities")

    _providers_loaded = True
