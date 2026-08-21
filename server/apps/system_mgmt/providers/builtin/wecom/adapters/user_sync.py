import requests

from apps.system_mgmt.providers.base import BaseUserSyncAdapter
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult

from .client import (
    WECOM_DEFAULT_USER_SYNC_DEPARTMENTS_URL,
    WECOM_DEFAULT_USER_SYNC_USERS_URL,
    _department_tree,
    _fetch_all_users,
    _get_access_token,
    _map_wecom_request_exception,
    _request_get,
    _resolved_url,
    _validate_credentials,
)


class WeComUserSyncAdapter(BaseUserSyncAdapter):
    capability_key = "user_sync"

    @classmethod
    def _departments(cls, config, token, root_department_id=""):
        url = _resolved_url(
            config, "user_sync_departments_url", WECOM_DEFAULT_USER_SYNC_DEPARTMENTS_URL
        )
        return _request_get(
            url,
            config,
            token,
            {"id": root_department_id} if root_department_id else {},
        ).get("department", [])

    @classmethod
    def list_departments(cls, config, provider_key, capability_key, **kwargs):
        error = _validate_credentials(config)
        if error:
            return error
        token, error = _get_access_token(config)
        if error:
            return error
        try:
            departments = cls._departments(config, token)
        except (ValueError, requests.Timeout, requests.RequestException) as error:
            return _map_wecom_request_exception(
                error,
                timeout_message="WeCom department request timed out",
                invalid_message="WeCom department response is invalid",
                request_failed_message="WeCom department request failed",
            )
        return CapabilityExecutionResult.success_result(
            "WeCom department options loaded",
            payload={"items": _department_tree(departments)},
        )

    @classmethod
    def sync_users(cls, config, provider_key, capability_key, **kwargs):
        error = _validate_credentials(config)
        if error:
            return error
        source = kwargs.get("source")
        business_config = getattr(source, "business_config", {}) or {}
        root_department_id = business_config.get("root_department_id")
        root_department_id = str(root_department_id) if root_department_id is not None else ""
        if root_department_id in {"", "0", "__all__", "**all**"}:
            return CapabilityExecutionResult.failed_result(
                "WeCom root department ID must be a real department ID",
                code="provider.invalid_config",
                field="root_department_id",
            )
        include_child = business_config.get("include_child_departments", True)
        token, error = _get_access_token(config)
        if error:
            return error
        try:
            departments = cls._departments(config, token, root_department_id)
        except (ValueError, requests.Timeout, requests.RequestException) as error:
            return _map_wecom_request_exception(
                error,
                timeout_message="WeCom department request timed out",
                invalid_message="WeCom department response is invalid",
                request_failed_message="WeCom department request failed",
            )
        if not include_child:
            departments = [
                item for item in departments if str(item.get("id")) == str(root_department_id)
            ]
        users_url = _resolved_url(
            config, "user_sync_users_url", WECOM_DEFAULT_USER_SYNC_USERS_URL
        )
        normalized_users, user_error = _fetch_all_users(
            config,
            token,
            users_url,
            {"department_id": root_department_id, "fetch_child": 1 if include_child else 0},
        )
        if user_error:
            return user_error
        return CapabilityExecutionResult.success_result(
            f"WeCom user sync payload fetched for source '{getattr(source, 'name', '')}'",
            payload={
                "group_list": [
                    {
                        "id": str(item["id"]),
                        "parent_id": str(item.get("parentid") or ""),
                        "name": item.get("name", ""),
                    }
                    for item in departments
                    if item.get("id") is not None
                ],
                "user_list": normalized_users,
            },
        )

    @classmethod
    def test_connection(cls, config, provider_key, capability_key, **kwargs):
        error = _validate_credentials(config)
        if error:
            return error
        _, error = _get_access_token(config)
        return error or CapabilityExecutionResult.success_result("WeCom user sync capability is ready")
