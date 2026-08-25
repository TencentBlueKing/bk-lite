from apps.system_mgmt.providers.runtime import CapabilityExecutionResult

from .client import _get_access_token, _validate_credentials


class WeComBaseConnectionAdapter:
    @classmethod
    def test_connection(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        error = _validate_credentials(config)
        if error:
            return error
        _, error = _get_access_token(config)
        return error or CapabilityExecutionResult.success_result("WeCom base connection is ready")
