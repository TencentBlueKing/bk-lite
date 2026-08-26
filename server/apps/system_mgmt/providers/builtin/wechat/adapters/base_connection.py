from apps.system_mgmt.providers.runtime import CapabilityExecutionResult


class WechatBaseConnectionAdapter:
    @classmethod
    def test_connection(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        app_id = (config or {}).get("app_id", "")
        app_secret = (config or {}).get("app_secret", "")
        if not app_id or not app_secret:
            return CapabilityExecutionResult.failed_result(
                "WeChat app_id or app_secret is missing",
                code="provider.invalid_config",
                field="app_id" if not app_id else "app_secret",
            )
        return CapabilityExecutionResult.success_result("WeChat base configuration is complete")
