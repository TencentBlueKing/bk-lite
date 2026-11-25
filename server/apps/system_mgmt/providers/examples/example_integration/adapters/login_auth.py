from apps.system_mgmt.providers.base import BaseLoginAuthAdapter
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult


class ExampleLoginAuthAdapter(BaseLoginAuthAdapter):
    @classmethod
    def test_connection(cls, config, provider_key, capability_key, **kwargs):
        return CapabilityExecutionResult.not_implemented(capability_key, "test_connection")

    @classmethod
    def build_login_url(cls, config, provider_key, capability_key, **kwargs):
        return CapabilityExecutionResult.not_implemented(capability_key, "build_login_url")

    @classmethod
    def authenticate(cls, config, provider_key, capability_key, **kwargs):
        return CapabilityExecutionResult.not_implemented(capability_key, "authenticate")
