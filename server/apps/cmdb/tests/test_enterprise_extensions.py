"""社区域 facade 经注册表取实现的纯单测（无注册→默认空契约）。"""

import pytest

from apps.cmdb.extensions import registry
from apps.cmdb.model_ops.extensions import (
    ModelEnterpriseExtension,
    get_model_enterprise_extension,
)
from apps.cmdb.instance_ops.extensions import (
    InstanceEnterpriseExtension,
    get_instance_enterprise_extension,
)
from apps.cmdb.collect.extensions import (
    CollectEnterpriseExtension,
    get_collect_enterprise_extension,
)


@pytest.fixture(autouse=True)
def _clear_registry():
    slots = ("model_ops", "instance_ops", "collect")
    saved = {s: registry._registry.get(s) for s in slots}
    for s in slots:
        registry._registry.pop(s, None)
    yield
    for s, v in saved.items():
        if v is not None:
            registry._registry[s] = v
        else:
            registry._registry.pop(s, None)


def test_model_default_when_unregistered():
    ext = get_model_enterprise_extension()
    assert isinstance(ext, ModelEnterpriseExtension)
    assert ext.file_attr_types() == set()
    assert ext.unsupported_unique_attr_types() == set()


def test_model_uses_registered_impl():
    class Custom(ModelEnterpriseExtension):
        def file_attr_types(self):
            return {"attachment", "image"}

    registry.register("model_ops", Custom())
    assert get_model_enterprise_extension().file_attr_types() == {"attachment", "image"}


def test_instance_default_is_noop():
    ext = get_instance_enterprise_extension()
    assert isinstance(ext, InstanceEnterpriseExtension)
    data = {"x": 1}
    assert ext.normalize_file_fields("m", data, [], operator="u") == data


def test_collect_default_empty():
    ext = get_collect_enterprise_extension()
    assert isinstance(ext, CollectEnterpriseExtension)
    assert ext.collect_tree == [] and ext.plugin_packages == ()
