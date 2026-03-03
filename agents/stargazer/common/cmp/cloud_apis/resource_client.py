# -*- coding: UTF-8 -*-
import importlib
import logging
from functools import partial, wraps
from pathlib import Path

from .collection import RESOURCE_COLLECTIONS

logger = logging.getLogger(__name__)


def _load_enterprise_plugins():
    """
    Scan and load enterprise CMP plugins from enterprise/cmp_plugins directory.
    This triggers the @register decorator to register plugins into ResourceClient.
    """
    base_dir = Path(__file__).parent.parent.parent.parent
    enterprise_plugins_dir = base_dir / "enterprise" / "cmp_plugins"

    if not enterprise_plugins_dir.exists():
        return

    for plugin_dir in enterprise_plugins_dir.iterdir():
        if not plugin_dir.is_dir() or plugin_dir.name.startswith(("_", ".")):
            continue

        resource_apis_dir = plugin_dir / "resource_apis"
        if not resource_apis_dir.exists():
            continue

        for py_file in resource_apis_dir.glob("cw_*.py"):
            module_name = (
                f"enterprise.cmp_plugins.{plugin_dir.name}.resource_apis.{py_file.stem}"
            )
            try:
                importlib.import_module(module_name)
                logger.debug(f"Loaded enterprise plugin: {module_name}")
            except Exception as e:
                logger.warning(f"Failed to load enterprise plugin {module_name}: {e}")


class ResourceClient(object):
    collection = {}

    def __init__(self, account, password, region, cloud_type, host="", **kwargs):
        self.account = account
        self.password = password
        self.region = region
        self.cloud_type = cloud_type
        self.host = host
        self.kwargs = kwargs

    @classmethod
    def set_component(cls, resource_component):
        cls.collection = resource_component

    @classmethod
    def update_component(cls, key, component_cls):
        cls.collection.update({key: component_cls})

    def __call__(self):
        pass

    def __getattr__(self, item):
        key = item + "_" + self.cloud_type.lower()
        if key in self.collection:
            class_path = self.collection[key]
            # 通过路径获取获取类
            module_name, class_name = class_path.rsplit(".", 1)
            _module = importlib.import_module(module_name)
            cls = getattr(_module, class_name)
            if not cls:
                raise AttributeError(
                    f"Cloud:{self.cloud_type} not define method `{item}`"
                )
            return cls(
                self.account, self.password, self.region, host=self.host, **self.kwargs
            )


ResourceClient.set_component(RESOURCE_COLLECTIONS)


def register(func=None, key="", **kwargs):
    if func is None:
        return partial(register, key=key)
    key = key or f"cw_{func.__name__[2:].lower()}"
    class_path = f"{func.__module__}.{func.__name__}"
    ResourceClient.update_component(key, class_path)

    @wraps(func)
    def inner(*args, **kwargs):
        return func(*args, **kwargs)

    return inner


_load_enterprise_plugins()
