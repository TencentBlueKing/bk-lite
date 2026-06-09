"""custom_reporting 社区契约：无注册时默认 no-op，社区不依赖企业实现。"""

import pytest

from apps.cmdb.extensions import registry
from apps.cmdb.custom_reporting.extensions import (
    CustomReportingExtension,
    get_custom_reporting_extension,
)


@pytest.fixture(autouse=True)
def _clear():
    registry._registry.pop("custom_reporting", None)
    yield
    registry._registry.pop("custom_reporting", None)


def test_default_noop():
    ext = get_custom_reporting_extension()
    assert isinstance(ext, CustomReportingExtension)
    assert ext.register_model_fields("m", []) == []
    assert ext.get_declared_attr_ids("m") == set()
    assert ext.normalize_identity_keys(None) == []
    ext.validate_instance_fields("m", [])
    ext.validate_relation_fields("m", [])
