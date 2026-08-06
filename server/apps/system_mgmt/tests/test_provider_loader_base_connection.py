from apps.system_mgmt.providers import loader
from apps.system_mgmt.providers.adapters.ad import ADBaseConnectionAdapter
from apps.system_mgmt.providers.adapters.feishu import FeishuBaseConnectionAdapter
from apps.system_mgmt.providers.adapters.wecom import WeComBaseConnectionAdapter
from apps.system_mgmt.providers.adapters.wechat import WechatBaseConnectionAdapter
from apps.system_mgmt.providers.registry import capability_adapter_registry


def test_loader_registers_ad_base_connection_adapter():
    loader.reset_builtin_providers()

    assert capability_adapter_registry.get("ad.base_connection") is ADBaseConnectionAdapter


def test_loader_registers_feishu_base_connection_adapter():
    loader.reset_builtin_providers()

    assert capability_adapter_registry.get("feishu.base_connection") is FeishuBaseConnectionAdapter


def test_loader_registers_wechat_base_connection_adapter():
    loader.reset_builtin_providers()

    assert capability_adapter_registry.get("wechat.base_connection") is WechatBaseConnectionAdapter


def test_loader_registers_wecom_base_connection_adapter():
    loader.reset_builtin_providers()

    assert capability_adapter_registry.get("wecom.base_connection") is WeComBaseConnectionAdapter
