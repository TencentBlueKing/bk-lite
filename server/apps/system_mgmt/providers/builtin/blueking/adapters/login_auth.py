from apps.system_mgmt.providers.base import BaseLoginAuthAdapter
from apps.system_mgmt.providers.log import logger
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult

from .client import _validate_credentials, get_login_username, test_esb_connection

_FAILED_TEMPLATE = "event=blueking_login_auth_failed binding_id=%s failed_stage=%s error_type=%s"
_TRANSPORT_CODES = {"provider.timeout", "provider.request_failed"}
_ERROR_TYPES = {
    "provider.timeout": "Timeout",
    "provider.auth_failed": "auth_rejected",
    "provider.request_failed": "request_failed",
    "provider.invalid_response": "invalid_response",
    "provider.invalid_config": "missing_token",
}


def _binding_id(kwargs):
    binding = kwargs.get("binding")
    raw_id = getattr(binding, "id", None)
    if type(raw_id) is not int:
        return ""
    return str(raw_id)


def _warn_authenticate_failure(binding_id, error_type):
    logger.warning(_FAILED_TEMPLATE, binding_id, "authenticate", error_type)


class BlueKingLoginAuthAdapter(BaseLoginAuthAdapter):
    capability_key = "login_auth"

    @classmethod
    def authenticate(cls, config, provider_key, capability_key, **kwargs):
        error = _validate_credentials(config)
        if error:
            return error
        binding_id = _binding_id(kwargs)
        bk_token = str(kwargs.get("bk_token") or "")
        if not bk_token:
            _warn_authenticate_failure(binding_id, "missing_token")
            return CapabilityExecutionResult.failed_result(
                "BlueKing login request is missing bk_token",
                code="provider.invalid_config",
                field="bk_token",
            )
        username, error = get_login_username(config, bk_token)
        if error:
            error_code = error.errors[0].code if error.errors else "provider.auth_failed"
            if error_code not in _TRANSPORT_CODES:
                _warn_authenticate_failure(binding_id, _ERROR_TYPES.get(error_code, error_code))
            return error
        return CapabilityExecutionResult.success_result(
            "BlueKing login authenticated",
            payload={"external_user": {"username": username}},
        )

    @classmethod
    def test_connection(cls, config, provider_key, capability_key, **kwargs):
        result = test_esb_connection(config)
        if result.success:
            return CapabilityExecutionResult.success_result("BlueKing login capability is ready")
        return result
