from apps.system_mgmt.providers.base import BaseUserSyncAdapter
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult

from .client import (
    ALL_DEPARTMENT_ID,
    INVALID_ROOT_DEPARTMENT_IDS,
    _validate_credentials,
    all_department_label,
    department_tree,
    group_list_from_departments,
    list_all_departments,
    list_all_users,
    normalize_users,
    scoped_departments,
    test_esb_connection,
)


class BlueKingUserSyncAdapter(BaseUserSyncAdapter):
    capability_key = "user_sync"

    @classmethod
    def list_departments(cls, config, provider_key, capability_key, **kwargs):
        error = _validate_credentials(config)
        if error:
            return error
        departments, error = list_all_departments(config)
        if error:
            return error
        forest = department_tree(departments)
        all_node = {
            "id": ALL_DEPARTMENT_ID,
            "name": all_department_label(kwargs.get("locale")),
            "parent_id": None,
            "children": forest,
            "selectable": True,
        }
        return CapabilityExecutionResult.success_result(
            "BlueKing department options loaded",
            payload={"items": [all_node]},
        )

    @classmethod
    def sync_users(cls, config, provider_key, capability_key, **kwargs):
        error = _validate_credentials(config)
        if error:
            return error
        source = kwargs.get("source")
        business_config = getattr(source, "business_config", None) or kwargs.get("business_config") or {}
        root_department_id = business_config.get("root_department_id")
        root_department_id = str(root_department_id) if root_department_id is not None else ""
        if root_department_id in INVALID_ROOT_DEPARTMENT_IDS:
            return CapabilityExecutionResult.failed_result(
                "BlueKing root department ID must be bk_all or a real department ID",
                code="provider.invalid_config",
                field="root_department_id",
            )
        include_child = business_config.get("include_child_departments", True)
        departments, error = list_all_departments(config)
        if error:
            return error
        if root_department_id == ALL_DEPARTMENT_ID:
            scoped = list(departments or [])
        else:
            scoped = scoped_departments(departments, root_department_id, include_child)
            if scoped is None:
                return CapabilityExecutionResult.failed_result(
                    "BlueKing root department ID must be bk_all or a real department ID",
                    code="provider.invalid_config",
                    field="root_department_id",
                )
        users, error = list_all_users(config)
        if error:
            return error
        selected_ids = [str(item.get("id")) for item in scoped if item.get("id") is not None]
        return CapabilityExecutionResult.success_result(
            "BlueKing user sync payload fetched",
            payload={
                "group_list": group_list_from_departments(
                    scoped,
                    attach_missing_parent_to=ALL_DEPARTMENT_ID if root_department_id == ALL_DEPARTMENT_ID else None,
                ),
                "user_list": normalize_users(users, selected_ids),
            },
        )

    @classmethod
    def test_connection(cls, config, provider_key, capability_key, **kwargs):
        result = test_esb_connection(config)
        if result.success:
            return CapabilityExecutionResult.success_result("BlueKing user sync capability is ready")
        return result
