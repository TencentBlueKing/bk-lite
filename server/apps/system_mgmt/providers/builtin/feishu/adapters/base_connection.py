from apps.system_mgmt.providers.runtime import CapabilityExecutionResult

from .client import _request_tenant_access_token


class FeishuBaseConnectionAdapter:
    @classmethod
    def test_connection(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        return _request_tenant_access_token(config, capability_key)
