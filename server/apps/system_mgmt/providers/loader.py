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
BUILTIN_IMPORT_PREFIX = "apps.system_mgmt.providers.builtin"
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


def _require_adapter_key_prefix(manifest_key: str, adapter_key: str) -> None:
    required_prefix = f"{manifest_key}."
    if not adapter_key.startswith(required_prefix):
        raise ValueError(
            f"Adapter key '{adapter_key}' must start with '{required_prefix}'"
        )


def _resolve_adapter_import_path(module_path: str, adapter_path: str, pack_dir: Path | None) -> str:
    if pack_dir is None:
        return adapter_path
    if adapter_path == module_path or adapter_path.startswith(f"{module_path}."):
        raise ValueError(
            f"Provider pack '{pack_dir.name}' must use a pack-relative adapter path, not '{adapter_path}'"
        )
    return f"{module_path}.{adapter_path}"


def _sync_uploaded_provider_packs() -> None:
    try:
        from apps.system_mgmt.enterprise.provider_pack_sync import sync_uploaded_provider_packs
    except ImportError:
        return
    sync_uploaded_provider_packs()


@contextmanager
def builtin_providers_read_lock():
    with _providers_load_lock:
        load_builtin_providers()
        _sync_uploaded_provider_packs()
        yield


def _already_registered_provider(provider_key: str) -> bool:
    return provider_key in provider_registry._providers


def _already_registered_adapter(adapter_key: str) -> bool:
    return adapter_key in capability_adapter_registry._adapters


def _register_provider_module(
    module_path: str,
    pack_dir: Path | None = None,
    *,
    expected_key: str | None = None,
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
    directory_key = expected_key if expected_key is not None else (pack_dir.name if pack_dir is not None else None)
    if directory_key is not None and directory_key != manifest.key:
        raise ValueError(
            f"Provider pack directory '{directory_key}' must match manifest key '{manifest.key}'"
        )
    if _already_registered_provider(manifest.key):
        raise ValueError(f"Provider '{manifest.key}' is already registered")

    if pack_dir is not None:
        manifest = manifest.model_copy(update={"pack_i18n": load_language_catalog(pack_dir)})

    adapter_pairs: list[tuple[str, type]] = []
    seen_adapter_keys: set[str] = set()
    for capability in manifest.capabilities:
        _require_adapter_key_prefix(manifest.key, capability.adapter_key)
        if capability.adapter_key in seen_adapter_keys or _already_registered_adapter(capability.adapter_key):
            raise ValueError(f"Adapter '{capability.adapter_key}' is already registered")
        seen_adapter_keys.add(capability.adapter_key)
        adapter_pairs.append(
            (
                capability.adapter_key,
                import_string(_resolve_adapter_import_path(module_path, capability.adapter_path, pack_dir)),
            )
        )

    if manifest.base_connection_adapter_key and manifest.base_connection_adapter_path:
        base_key = manifest.base_connection_adapter_key
        _require_adapter_key_prefix(manifest.key, base_key)
        if base_key in seen_adapter_keys or _already_registered_adapter(base_key):
            raise ValueError(f"Adapter '{base_key}' is already registered")
        adapter_pairs.append(
            (
                base_key,
                import_string(
                    _resolve_adapter_import_path(module_path, manifest.base_connection_adapter_path, pack_dir)
                ),
            )
        )

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
    expected_key: str | None = None,
) -> None:
    pack_name = expected_key or (pack_dir.name if pack_dir is not None else module_path)
    try:
        _register_provider_module(module_path, pack_dir, expected_key=expected_key)
    except Exception:
        logger.exception("Failed to load provider pack '%s'; skipping", pack_name)


def register_uploaded_provider_pack(module_path: str, pack_dir: Path, expected_key: str) -> None:
    _register_provider_module(module_path, pack_dir, expected_key=expected_key)


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

        for module_path, pack_dir in builtin_packs:
            _try_load_pack(module_path, pack_dir)

        _providers_loaded = True


def reset_builtin_providers():
    global _providers_loaded

    with _providers_load_lock:
        provider_registry.clear()
        capability_adapter_registry.clear()
        _providers_loaded = False
        try:
            from apps.system_mgmt.enterprise.provider_pack_sync import reset_sync_cache
        except ImportError:
            pass
        else:
            reset_sync_cache()
