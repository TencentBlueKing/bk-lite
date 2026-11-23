from apps.system_mgmt.providers.runtime import CapabilityExecutionResult


class ExampleBaseConnectionAdapter:
    @classmethod
    def test_connection(cls, config, provider_key, capability_key, **kwargs):
        return CapabilityExecutionResult.not_implemented(capability_key, "test_connection")
