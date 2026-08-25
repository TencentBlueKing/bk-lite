from apps.system_mgmt.providers.runtime import CapabilityExecutionResult

from . import client


class ADBaseConnectionAdapter:
    @classmethod
    def test_connection(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        try:
            connection_config = client.build_connection_config(config, require_base_dn=False)
            if not all([connection_config.connection_url, connection_config.bind_dn, connection_config.bind_password]):
                return CapabilityExecutionResult.failed_result(
                    "AD connection configuration is incomplete",
                    code="provider.invalid_config",
                )
            client.probe_root_dse(connection_config)
        except Exception as error:
            return client._build_ad_connection_failure(error)
        return CapabilityExecutionResult.success_result("AD base connection is ready")
