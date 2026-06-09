import importlib
import pkgutil

from apps.core.logger import cmdb_logger as logger


class CollectionPluginLoader:
    _loaded = False
    _package_names = [
        "apps.cmdb.collection.plugins.community",
    ]

    @classmethod
    def load_plugins(cls):
        if cls._loaded:
            return True

        from apps.cmdb.collect.extensions import get_collect_enterprise_extension

        # 社区基础包 + 企业采集插件包（经 collect 门面发现，缺企业时为空）
        package_names = list(
            dict.fromkeys([*cls._package_names, *get_collect_enterprise_extension().plugin_packages])
        )

        has_error = False
        for package_name in package_names:
            if not cls._load_package(package_name):
                has_error = True

        cls._loaded = not has_error
        return cls._loaded

    @classmethod
    def _load_package(cls, package_name: str):
        try:
            package = importlib.import_module(package_name)
        except ModuleNotFoundError as exc:
            if exc.name == package_name:
                logger.debug("Collection plugin package not found: %s", package_name)
                return True
            logger.error("Failed to import collection plugin package %s: %s", package_name, exc)
            return False
        except Exception as exc:  # noqa: BLE001 - 插件加载失败不能阻塞全局能力
            logger.error("Failed to import collection plugin package %s: %s", package_name, exc)
            return False

        package_paths = getattr(package, "__path__", None)
        if not package_paths:
            return True

        has_error = False

        for _, module_name, _ in pkgutil.walk_packages(package_paths, prefix=f"{package_name}."):
            base_name = module_name.rsplit(".", 1)[-1]
            if base_name.startswith("_"):
                continue
            try:
                importlib.import_module(module_name)
            except Exception as exc:  # noqa: BLE001 - 单个插件失败不影响其他插件注册
                logger.error("Failed to import collection plugin module %s: %s", module_name, exc)
                has_error = True

        return not has_error