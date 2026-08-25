from contextlib import contextmanager
from importlib import import_module
from pathlib import Path
from threading import RLock

from django.utils.module_loading import import_string

from apps.core.logger import system_mgmt_logger as logger

from .pack_i18n import load_language_catalog
from .registry import capability_adapter_registry, provider_registry
from .schemas import ProviderManifest

BUILTIN_PROVIDER_ROOT = Path(__file__).resolve().parent / "builtin"
CUSTOM_PROVIDER_ROOT = Path(__file__).resolve().parent / "custom"
BUILTIN_IMPORT_PREFIX = "apps.system_mgmt.providers.builtin"
CUSTOM_IMPORT_PREFIX = "apps.system_mgmt.providers.custom"
_SKIP_DIR_NAMES = {"__pycache__"}
_REQUIRED_PACK_FILES = ("__init__.py", "adapters/client.py", "adapters/base_connection.py")

_providers_loaded = False
_providers_load_lock = RLock()


def iter_pack_directories(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    children: list[Path] = []
    for child in sorted(root.iterdir(), key=lambda path: path.name):
        if not child.is_dir() or child.name in _SKIP_DIR_NAMES or child.name.startswith("."):
            continue
        children.append(child)
    return children


def validate_pack_layout(pack_dir: Path) -> None:
    missing = [relative for relative in _REQUIRED_PACK_FILES if not (pack_dir / relative).is_file()]
    if missing:
        raise ValueError(f"Provider pack '{pack_dir.name}' is missing {', '.join(missing)}")


def discover_provider_packs(
    root: Path,
    import_prefix: str,
    *,
    required: bool = True,
) -> list[tuple[str, Path]]:
    if not root.is_dir():
        if required:
            raise ValueError(f"Provider root does not exist: {root}")
        return []
    return [(f"{import_prefix}.{child.name}", child) for child in iter_pack_directories(root)]


def discover_builtin_provider_packs(root: Path | None = None) -> list[tuple[str, Path]]:
    return discover_provider_packs(root or BUILTIN_PROVIDER_ROOT, BUILTIN_IMPORT_PREFIX, required=True)


def discover_custom_provider_packs(root: Path | None = None) -> list[tuple[str, Path]]:
    return discover_provider_packs(root or CUSTOM_PROVIDER_ROOT, CUSTOM_IMPORT_PREFIX, required=False)


@contextmanager
def builtin_providers_read_lock():
    with _providers_load_lock:
        load_builtin_providers()
        yield


def _already_registered_provider(provider_key: str) -> bool:
    return provider_key in provider_registry._providers


def _already_registered_adapter(adapter_key: str) -> bool:
    return adapter_key in capability_adapter_registry._adapters


def _register_provider_module(
    module_path: str,
    pack_dir: Path | None = None,
    *,
    reserved_keys: frozenset[str] = frozenset(),
):
    if pack_dir is not None:
        validate_pack_layout(pack_dir)

    module = import_module(module_path)
    raw_manifest = getattr(module, "PROVIDER_MANIFEST", None)
    if raw_manifest is None:
        raise ValueError(f"Provider module '{module_path}' does not expose PROVIDER_MANIFEST")

    manifest = (
        raw_manifest if isinstance(raw_manifest, ProviderManifest) else ProviderManifest.model_validate(raw_manifest)
    )
    if pack_dir is not None and pack_dir.name != manifest.key:
        raise ValueError(
            f"Provider pack directory '{pack_dir.name}' must match manifest key '{manifest.key}'"
        )
    if manifest.key in reserved_keys or _already_registered_provider(manifest.key):
        raise ValueError(f"Provider '{manifest.key}' is already registered")

    if pack_dir is not None:
        manifest = manifest.model_copy(update={"pack_i18n": load_language_catalog(pack_dir)})

    adapter_pairs: list[tuple[str, type]] = []
    seen_adapter_keys: set[str] = set()
    for capability in manifest.capabilities:
        if capability.adapter_key in seen_adapter_keys or _already_registered_adapter(capability.adapter_key):
            raise ValueError(f"Adapter '{capability.adapter_key}' is already registered")
        seen_adapter_keys.add(capability.adapter_key)
        adapter_pairs.append((capability.adapter_key, import_string(capability.adapter_path)))

    if manifest.base_connection_adapter_key and manifest.base_connection_adapter_path:
        base_key = manifest.base_connection_adapter_key
        if base_key in seen_adapter_keys or _already_registered_adapter(base_key):
            raise ValueError(f"Adapter '{base_key}' is already registered")
        adapter_pairs.append((base_key, import_string(manifest.base_connection_adapter_path)))

    provider_registry.register(manifest)
    try:
        for adapter_key, adapter_cls in adapter_pairs:
            capability_adapter_registry.register(adapter_key, adapter_cls)
    except Exception:
        provider_registry._providers.pop(manifest.key, None)
        for adapter_key, _ in adapter_pairs:
            capability_adapter_registry._adapters.pop(adapter_key, None)
        raise

    logger.debug(
        f"Loaded provider manifest '{manifest.key}' with {len(manifest.capabilities)} capabilities"
    )


def _try_load_pack(
    module_path: str,
    pack_dir: Path | None,
    *,
    reserved_keys: frozenset[str],
) -> None:
    pack_name = pack_dir.name if pack_dir is not None else module_path
    try:
        _register_provider_module(module_path, pack_dir, reserved_keys=reserved_keys)
    except Exception:
        logger.exception("Failed to load provider pack '%s'; skipping", pack_name)


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

        builtin_packs = discover_builtin_provider_packs()
        reserved_builtin_keys = frozenset(pack_dir.name for _, pack_dir in builtin_packs if pack_dir is not None)

        for module_path, pack_dir in builtin_packs:
            _try_load_pack(module_path, pack_dir, reserved_keys=frozenset())

        for module_path, pack_dir in discover_custom_provider_packs():
            _try_load_pack(module_path, pack_dir, reserved_keys=reserved_builtin_keys)

        _providers_loaded = True


def reset_builtin_providers():
    global _providers_loaded

    with _providers_load_lock:
        provider_registry.clear()
        capability_adapter_registry.clear()
        _providers_loaded = False
