import pytest

from apps.cmdb.services.network_config_file_policy import (
    SUPPORTED_NETWORK_CONFIG_MODELS,
    get_supported_brand_options,
    resolve_device_type,
    validate_network_config_instance,
)
from apps.core.exceptions.base_app_exception import BaseAppException


def test_supported_models_are_only_mvp_network_models():
    assert SUPPORTED_NETWORK_CONFIG_MODELS == {"switch", "router", "firewall", "loadbalance"}


@pytest.mark.parametrize(
    ("brand", "expected"),
    [
        ("华为", "huawei"),
        ("Huawei", "huawei"),
        ("H3C", "hp_comware"),
        ("HP Comware", "hp_comware"),
        ("Cisco", "cisco_ios"),
        ("Juniper", "juniper_junos"),
        ("F5", "f5_tmsh"),
        ("Fortinet", "fortinet"),
    ],
)
def test_resolve_device_type_normalizes_supported_brand_aliases(brand, expected):
    assert resolve_device_type(brand) == expected


def test_resolve_device_type_rejects_empty_brand():
    with pytest.raises(BaseAppException, match="缺少厂商"):
        resolve_device_type("")


def test_resolve_device_type_rejects_unsupported_brand():
    with pytest.raises(BaseAppException, match="暂不支持"):
        resolve_device_type("UnknownVendor")


def test_validate_network_config_instance_requires_supported_model_and_brand():
    instance = {"_id": 11, "model_id": "switch", "brand": "Cisco", "ip_addr": "10.0.0.1"}

    result = validate_network_config_instance(instance)

    assert result["device_type"] == "cisco_ios"
    assert result["host"] == "10.0.0.1"


def test_validate_network_config_instance_rejects_non_mvp_model():
    with pytest.raises(BaseAppException, match="仅支持"):
        validate_network_config_instance({"model_id": "host", "brand": "Cisco", "ip_addr": "10.0.0.1"})


def test_get_supported_brand_options_is_frontend_friendly():
    options = get_supported_brand_options()

    assert {"label": "Cisco", "device_type": "cisco_ios"} in options
    assert any("华为" in item["label"] for item in options)
