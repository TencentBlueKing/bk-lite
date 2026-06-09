"""ModelManage 的 custom_reporting 方法经契约委托；无注册时安全 no-op。"""

import pytest
from apps.cmdb.extensions import registry
from apps.cmdb.services.model import ModelManage


@pytest.fixture(autouse=True)
def _clear():
    registry._registry.pop("custom_reporting", None)
    yield
    registry._registry.pop("custom_reporting", None)


def test_register_fields_noop_without_overlay():
    assert ModelManage.register_custom_reporting_model_fields("m", []) == []


def test_declared_attr_ids_empty_without_overlay():
    assert ModelManage._get_custom_reporting_declared_attr_ids("m") == set()


def test_delegates_to_registered_extension():
    from apps.cmdb.custom_reporting.extensions import CustomReportingExtension

    class Impl(CustomReportingExtension):
        def get_declared_attr_ids(self, model_id):
            return {"a", "b"}

    registry.register("custom_reporting", Impl())
    assert ModelManage._get_custom_reporting_declared_attr_ids("m") == {"a", "b"}
