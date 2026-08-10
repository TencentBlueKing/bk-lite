import importlib

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Union

from core.logger import logger


@dataclass
class PluginResolution:
    model_id: str
    source: str
    plugin_path: Path
    plugin_root: Path
    has_oss_fallback: bool = False
    fallback_plugin_path: Optional[Path] = None
    config: Optional[Dict[str, Any]] = None
    fallback_config: Optional[Dict[str, Any]] = None


class PluginSourceResolver:
    def __init__(
        self,
        oss_plugins_base_dir: Optional[Union[str, Path]] = None,
        enterprise_root: Optional[Union[str, Path]] = None,
        enterprise_package: str = 'enterprise'
    ):
        self.oss_plugins_base_dir = Path(oss_plugins_base_dir) if oss_plugins_base_dir else Path('plugins/inputs')
        self.base_dir = self.oss_plugins_base_dir.parent.parent
        self.enterprise_root = Path(enterprise_root) if enterprise_root else self.base_dir / 'enterprise'
        self.enterprise_plugins_base_dir = self.enterprise_root / 'plugins' / 'inputs'
        self.enterprise_package = enterprise_package
        self._resolution_cache: Dict[tuple[str, bool], PluginResolution] = {}
        self._enterprise_available: Optional[bool] = None

    def is_enterprise_available(self) -> bool:
        if self._enterprise_available is not None:
            return self._enterprise_available

        if not self.enterprise_root.exists():
            self._enterprise_available = False
            return self._enterprise_available

        if not self.enterprise_plugins_base_dir.exists():
            self._enterprise_available = False
            return self._enterprise_available

        try:
            importlib.import_module(self.enterprise_package)
        except ImportError as exc:
            logger.debug(f'Enterprise package unavailable, skipping enterprise plugins: {exc}')
            self._enterprise_available = False
            return self._enterprise_available

        self._enterprise_available = True
        return self._enterprise_available

    def resolve(self, model_id: str, prefer_enterprise: bool = True) -> PluginResolution:
        cache_key = (model_id, prefer_enterprise)
        if cache_key in self._resolution_cache:
            return self._resolution_cache[cache_key]

        oss_plugin_path = self.oss_plugins_base_dir / model_id / 'plugin.yml'
        enterprise_plugin_path = self.enterprise_plugins_base_dir / model_id / 'plugin.yml'

        enterprise_available = self.is_enterprise_available()
        has_enterprise_plugin = enterprise_available and enterprise_plugin_path.exists()
        has_oss_plugin = oss_plugin_path.exists()

        if has_enterprise_plugin and has_oss_plugin:
            logger.info(
                f'Plugin source conflict detected: model_id={model_id}, '
                f'enterprise_path={enterprise_plugin_path}, oss_path={oss_plugin_path}, '
                'final_selected_source=enterprise'
            )

        if prefer_enterprise and has_enterprise_plugin:
            resolution = PluginResolution(
                model_id=model_id,
                source='enterprise',
                plugin_path=enterprise_plugin_path,
                plugin_root=enterprise_plugin_path.parent,
                has_oss_fallback=has_oss_plugin,
                fallback_plugin_path=oss_plugin_path if has_oss_plugin else None
            )
        elif has_oss_plugin:
            resolution = PluginResolution(
                model_id=model_id,
                source='oss',
                plugin_path=oss_plugin_path,
                plugin_root=oss_plugin_path.parent,
                has_oss_fallback=False,
                fallback_plugin_path=None
            )
        elif has_enterprise_plugin:
            resolution = PluginResolution(
                model_id=model_id,
                source='enterprise',
                plugin_path=enterprise_plugin_path,
                plugin_root=enterprise_plugin_path.parent,
                has_oss_fallback=False,
                fallback_plugin_path=None
            )
        else:
            checked_paths = [str(oss_plugin_path)]
            if enterprise_available:
                checked_paths.insert(0, str(enterprise_plugin_path))
            raise FileNotFoundError(
                f"Plugin config not found for model '{model_id}'. Checked paths: {checked_paths}"
            )

        logger.info(
            f'Plugin resolved: model_id={model_id}, selected_source={resolution.source}, '
            f'selected_plugin_path={resolution.plugin_path}, has_fallback={resolution.has_oss_fallback}'
        )
        self._resolution_cache[cache_key] = resolution
        return resolution

    def clear_cache(self):
        self._resolution_cache.clear()
        self._enterprise_available = None


plugin_source_resolver = PluginSourceResolver()
