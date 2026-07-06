from apps.core.logger import logger

from ..runtime import CapabilityExecutionResult


class BaseCapabilityAdapter:
    capability_key = ""

    @classmethod
    def test_connection(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        logger.warning(f"Capability adapter '{cls.__name__}' does not implement test_connection for provider '{provider_key}'")
        return CapabilityExecutionResult.not_implemented(capability_key, "test_connection")


class BaseLoginAuthAdapter(BaseCapabilityAdapter):
    capability_key = "login_auth"

    @classmethod
    def build_login_url(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        return CapabilityExecutionResult.not_implemented(capability_key, "build_login_url")

    @classmethod
    def authenticate(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        return CapabilityExecutionResult.not_implemented(capability_key, "authenticate")


class BaseUserSyncAdapter(BaseCapabilityAdapter):
    capability_key = "user_sync"

    @classmethod
    def sync_users(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        return CapabilityExecutionResult.not_implemented(capability_key, "sync_users")

    @classmethod
    def list_departments(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        return CapabilityExecutionResult.success_result(
            "Department list loaded",
            payload={
                "items": [
                    {
                        "id": "__all__",
                        "name": "全部部门",
                        "parent_id": None,
                        "children": [],
                        "selectable": True,
                        "is_all": True,
                    }
                ],
                "all_department_id": "0",
            },
        )


class BaseIMNotificationAdapter(BaseCapabilityAdapter):
    capability_key = "im_notification"

    @classmethod
    def list_external_users(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        return CapabilityExecutionResult.not_implemented(capability_key, "list_external_users")

    @classmethod
    def send_message(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        return CapabilityExecutionResult.not_implemented(capability_key, "send_message")
