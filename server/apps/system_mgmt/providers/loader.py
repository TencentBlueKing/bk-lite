from contextlib import contextmanager
from importlib import import_module
from threading import RLock

from django.utils.module_loading import import_string

from apps.core.logger import logger

from .registry import capability_adapter_registry, provider_registry
from .schemas import ProviderManifest

BUILTIN_PROVIDER_MODULES = (
    "apps.system_mgmt.providers.manifests.feishu",
    "apps.system_mgmt.providers.manifests.wechat",
    "apps.system_mgmt.providers.manifests.ad",
)

_providers_loaded = False
_providers_load_lock = RLock()


@contextmanager
def builtin_providers_read_lock():
    with _providers_load_lock:
        load_builtin_providers()
        yield


def load_builtin_providers(force: bool = False):
    global _providers_loaded

    if _providers_loaded and not force:
        return

    with _providers_load_lock:
        if _providers_loaded and not force:
            return

        provider_registry.clear()
        capability_adapter_registry.clear()
        _providers_loaded = False

        try:
            for module_path in BUILTIN_PROVIDER_MODULES:
                module = import_module(module_path)
                raw_manifest = getattr(module, "PROVIDER_MANIFEST", None)
                if raw_manifest is None:
                    raise ValueError(f"Provider module '{module_path}' does not expose PROVIDER_MANIFEST")

                manifest = (
                    raw_manifest
                    if isinstance(raw_manifest, ProviderManifest)
                    else ProviderManifest.model_validate(raw_manifest)
                )
                provider_registry.register(manifest)

                for capability in manifest.capabilities:
                    adapter_cls = import_string(capability.adapter_path)
                    capability_adapter_registry.register(capability.adapter_key, adapter_cls)

                logger.debug(
                    f"Loaded provider manifest '{manifest.key}' "
                    f"with {len(manifest.capabilities)} capabilities"
                )
        except Exception:
            provider_registry.clear()
            capability_adapter_registry.clear()
            raise

        _providers_loaded = True


def reset_builtin_providers():
    global _providers_loaded

    with _providers_load_lock:
        provider_registry.clear()
        capability_adapter_registry.clear()
        _providers_loaded = False
