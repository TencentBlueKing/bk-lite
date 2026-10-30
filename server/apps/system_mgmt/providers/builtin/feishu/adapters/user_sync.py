import time
from concurrent.futures import ThreadPoolExecutor

from apps.system_mgmt.providers.base import BaseUserSyncAdapter
from apps.system_mgmt.providers.log import logger
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult

from .client import (
    FEISHU_COMPANY_ROOT_DEPARTMENT_ID,
    FEISHU_COMPANY_ROOT_DEPARTMENT_NAME,
    FEISHU_CONTACT_SCOPES_URL,
    FEISHU_DEFAULT_DEPARTMENT_ID_TYPE,
    FEISHU_DEPARTMENT_CHILDREN_MAX_WORKERS,
    FEISHU_DEPARTMENTS_BATCH_URL,
    FEISHU_USERS_BY_DEPARTMENT_URL,
    _feishu_get_paginated,
    _fetch_company_root_children,
    _fetch_department_children,
    _fetch_tenant_access_token,
    _get_config_value,
    _get_feishu_department_identifier,
    _request_tenant_access_token,
)

FEISHU_SYNC_USER_FIELDS = "department_ids,user_id,open_id,name,email,mobile," "job_title,employee_no,job_level_id,leader_user_id,status,custom_attrs"
_FEISHU_RESERVED_USER_KEYS = frozenset(
    {
        "user_id",
        "open_id",
        "name",
        "email",
        "mobile",
        "job_title",
        "employee_no",
        "job_level_id",
        "leader_user_id",
        "is_resigned",
        "is_frozen",
        "department_ids",
    }
)


def _feishu_flag(value):
    if value is True:
        return "true"
    if value is False:
        return "false"
    return ""


def _feishu_profile(item):
    status = item.get("status") if isinstance(item.get("status"), dict) else {}
    return {
        "job_title": str(item.get("job_title") or ""),
        "employee_no": str(item.get("employee_no") or ""),
        "job_level_id": str(item.get("job_level_id") or ""),
        "leader_user_id": str(item.get("leader_user_id") or ""),
        "is_resigned": _feishu_flag(status.get("is_resigned")),
        "is_frozen": _feishu_flag(status.get("is_frozen")),
    }


def _feishu_custom_attr_text(attr):
    value = attr.get("value") if isinstance(attr.get("value"), dict) else {}
    generic_user = value.get("generic_user") if isinstance(value.get("generic_user"), dict) else {}
    for candidate in (value.get("text"), value.get("option_value"), value.get("url"), generic_user.get("id")):
        text = str(candidate or "").strip()
        if text:
            return text
    return ""


def _feishu_custom_fields(item):
    attrs = item.get("custom_attrs")
    if not isinstance(attrs, list):
        return {}
    fields = {}
    for attr in attrs:
        if not isinstance(attr, dict):
            continue
        attr_id = str(attr.get("id") or "").strip()
        if not attr_id or attr_id in _FEISHU_RESERVED_USER_KEYS or attr_id in fields:
            continue
        text = _feishu_custom_attr_text(attr)
        if text:
            fields[attr_id] = text
    return fields


def _feishu_user_record(item):
    return {
        "user_id": item.get("user_id", ""),
        "open_id": item.get("open_id", ""),
        "name": item.get("name", ""),
        "email": item.get("email", ""),
        "mobile": item.get("mobile", ""),
        **_feishu_profile(item),
        **_feishu_custom_fields(item),
        "department_ids": [str(value) for value in item.get("department_ids") or []],
    }


class FeishuUserSyncAdapter(BaseUserSyncAdapter):
    capability_key = "user_sync"

    @classmethod
    def normalize_business_config(cls, business_config: dict | None) -> dict:
        normalized = super().normalize_business_config(business_config)
        # 拉子部门是适配器实现默认，不再作为用户配置；去掉旧字段以免契约校验失败。
        normalized.pop("fetch_child", None)
        return normalized

    @classmethod
    def test_connection(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        return _request_tenant_access_token(config, capability_key)

    @classmethod
    def list_departments(cls, config: dict, provider_key: str, capability_key: str, **kwargs):  # noqa: C901
        operation_started_at = time.perf_counter()
        source = kwargs.get("source")
        business_config = kwargs.get("business_config") or {}
        source_business_config = getattr(source, "business_config", None) or {}
        merged_business_config = {**source_business_config, **business_config}

        token_started_at = time.perf_counter()
        tenant_access_token, error = _fetch_tenant_access_token(config)
        token_duration_ms = round((time.perf_counter() - token_started_at) * 1000)
        if error:
            return error

        department_id_type = merged_business_config.get("department_id_type")
        department_params: dict = {"page_size": 50}
        if department_id_type:
            department_params["department_id_type"] = department_id_type

        nodes: dict[str, dict] = {}
        external_request_id = ""
        scope_root_ids: list[str] = []
        scopes_duration_ms = 0
        root_details_duration_ms = 0
        children_duration_ms = 0

        def upsert_node(item: dict, fallback_parent_id: str | None = None):
            department_id = _get_feishu_department_identifier(item, department_id_type)
            if not department_id:
                return None
            department_id = str(department_id)

            parent_id = item.get("parent_department_id")
            parent_id = str(parent_id) if parent_id not in (None, "") else fallback_parent_id
            node = nodes.get(department_id)
            if node is None:
                node = {"id": department_id, "name": item.get("name") or department_id, "parent_id": parent_id}
                nodes[department_id] = node
            else:
                node["name"] = item.get("name") or node["name"]
                node["parent_id"] = parent_id
            return department_id

        company_root_started_at = time.perf_counter()
        company_root_payload, company_root_error = _fetch_company_root_children(config, tenant_access_token)
        company_root_duration_ms = round((time.perf_counter() - company_root_started_at) * 1000)
        if company_root_error:
            return company_root_error

        if company_root_payload is not None:
            department_id_type = FEISHU_DEFAULT_DEPARTMENT_ID_TYPE
            scope_root_ids = [FEISHU_COMPANY_ROOT_DEPARTMENT_ID]
            external_request_id = company_root_payload.get("request_id") or ""
            nodes[FEISHU_COMPANY_ROOT_DEPARTMENT_ID] = {
                "id": FEISHU_COMPANY_ROOT_DEPARTMENT_ID,
                "name": FEISHU_COMPANY_ROOT_DEPARTMENT_NAME,
                "parent_id": None,
            }
            for child in company_root_payload["items"]:
                upsert_node(child, FEISHU_COMPANY_ROOT_DEPARTMENT_ID)
        else:
            scopes_started_at = time.perf_counter()
            scopes_payload, error = _feishu_get_paginated(
                _get_config_value(config, "user_sync_scopes_url", FEISHU_CONTACT_SCOPES_URL),
                tenant_access_token,
                params=department_params,
                config=config,
                item_key="department_ids",
            )
            if error:
                return error
            scopes_duration_ms = round((time.perf_counter() - scopes_started_at) * 1000)

            invalid_scope_root_ids = {"", FEISHU_COMPANY_ROOT_DEPARTMENT_ID, "__all__", "**all**"}
            for department_id in scopes_payload["items"]:
                normalized_id = str(department_id or "").strip()
                if normalized_id not in invalid_scope_root_ids and normalized_id not in scope_root_ids:
                    scope_root_ids.append(normalized_id)

            external_request_id = scopes_payload.get("request_id") or ""

            root_details_started_at = time.perf_counter()
            for start in range(0, len(scope_root_ids), 50):
                detail_payload, error = _feishu_get_paginated(
                    _get_config_value(config, "user_sync_departments_batch_url", FEISHU_DEPARTMENTS_BATCH_URL),
                    tenant_access_token,
                    params={
                        "department_ids": scope_root_ids[start : start + 50],
                        **({"department_id_type": department_id_type} if department_id_type else {}),
                    },
                    config=config,
                )
                if error:
                    return error
                external_request_id = detail_payload.get("request_id") or external_request_id
                for department in detail_payload["items"]:
                    upsert_node(department)
            root_details_duration_ms = round((time.perf_counter() - root_details_started_at) * 1000)

            children_params = {**department_params, "fetch_child": "true"}

            def fetch_children(scope_root_id: str):
                child_payload, child_error = _fetch_department_children(config, tenant_access_token, scope_root_id, children_params)
                return scope_root_id, child_payload, child_error

            children_started_at = time.perf_counter()
            if scope_root_ids:
                with ThreadPoolExecutor(max_workers=min(FEISHU_DEPARTMENT_CHILDREN_MAX_WORKERS, len(scope_root_ids))) as executor:
                    child_requests = [executor.submit(fetch_children, scope_root_id) for scope_root_id in scope_root_ids]
                    for child_request in child_requests:
                        _scope_root_id, child_payload, error = child_request.result()
                        if error:
                            return error
                        external_request_id = child_payload.get("request_id") or external_request_id
                        for child in child_payload["items"]:
                            upsert_node(child, _scope_root_id)
            children_duration_ms = round((time.perf_counter() - children_started_at) * 1000)

        child_ids_by_parent: dict[str, list[str]] = {}
        roots = []
        for node in nodes.values():
            parent_id = node["parent_id"]
            if not parent_id or parent_id not in nodes:
                node["parent_id"] = None

        processed_ids = set()
        for department_id in nodes:
            if department_id in processed_ids:
                continue

            path = []
            position = {}
            current_id = department_id
            while current_id and current_id in nodes and current_id not in processed_ids:
                if current_id in position:
                    cycle_entry_id = path[position[current_id]]
                    nodes[cycle_entry_id]["parent_id"] = None
                    break
                position[current_id] = len(path)
                path.append(current_id)
                current_id = nodes[current_id]["parent_id"]
            processed_ids.update(path)

        for node in nodes.values():
            parent_id = node["parent_id"]
            if parent_id:
                child_ids_by_parent.setdefault(parent_id, []).append(node["id"])
            else:
                roots.append(node["id"])

        def build_node(department_id: str):
            node = nodes[department_id]
            return {
                "id": node["id"],
                "name": node["name"],
                "parent_id": node["parent_id"],
                "children": [build_node(child_id) for child_id in child_ids_by_parent.get(department_id, [])],
                "selectable": True,
            }

        total_duration_ms = round((time.perf_counter() - operation_started_at) * 1000)
        server_timing = ", ".join(
            [
                f"feishu-token;dur={token_duration_ms}",
                f"feishu-company-root;dur={company_root_duration_ms}",
                f"feishu-scopes;dur={scopes_duration_ms}",
                f"feishu-root-details;dur={root_details_duration_ms}",
                f"feishu-children;dur={children_duration_ms}",
                f"feishu-total;dur={total_duration_ms}",
            ]
        )
        logger.debug(f"Feishu department options timing: roots={len(scope_root_ids)}, {server_timing}")
        return CapabilityExecutionResult.success_result(
            "Feishu department options loaded",
            payload={
                "items": [build_node(root_id) for root_id in roots],
                "external_request_id": external_request_id,
                "server_timing": server_timing,
            },
        )

    @classmethod
    def sync_users(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        # Local import avoids circular dependency: adapters -> service -> providers -> adapters
        from apps.system_mgmt.services.user_sync_service import get_user_sync_business_value

        source = kwargs.get("source")
        root_department_id = str(get_user_sync_business_value(source, "root_department_id", "") or "").strip()
        if root_department_id in {"", "__all__", "**all**"}:
            return CapabilityExecutionResult.failed_result(
                "Feishu user synchronization requires a visible department root",
                code="provider.invalid_config",
                field="root_department_id",
            )

        tenant_access_token, error = _fetch_tenant_access_token(config)
        if error:
            return error

        department_id_type = get_user_sync_business_value(source, "department_id_type", None)
        user_id_type = get_user_sync_business_value(source, "user_id_type", None)
        if root_department_id == FEISHU_COMPANY_ROOT_DEPARTMENT_ID:
            department_id_type = FEISHU_DEFAULT_DEPARTMENT_ID_TYPE

        dept_params: dict = {"page_size": 50, "fetch_child": "true"}
        if department_id_type:
            dept_params["department_id_type"] = department_id_type

        department_payload, error = _fetch_department_children(config, tenant_access_token, root_department_id, dept_params)
        if error:
            return error

        group_list = []
        department_ids = [str(root_department_id)]
        for item in department_payload["items"]:
            department_id = _get_feishu_department_identifier(item, department_id_type)
            if not department_id:
                continue
            department_id = str(department_id)
            group_list.append(
                {
                    "id": department_id,
                    "parent_id": str(item.get("parent_department_id") or root_department_id),
                    "name": item.get("name") or str(department_id),
                }
            )
            if department_id not in department_ids:
                department_ids.append(department_id)

        users_by_identity = {}
        external_request_id = department_payload.get("request_id") or ""
        for department_id in department_ids:
            user_params: dict = {
                "department_id": department_id,
                "fetch_child": "true",
                "page_size": 50,
                "fields": FEISHU_SYNC_USER_FIELDS,
            }
            if user_id_type:
                user_params["user_id_type"] = user_id_type
            if department_id_type:
                user_params["department_id_type"] = department_id_type

            user_payload, error = _feishu_get_paginated(
                _get_config_value(config, "user_sync_users_url", FEISHU_USERS_BY_DEPARTMENT_URL),
                tenant_access_token,
                params=user_params,
                config=config,
            )
            if error:
                return error

            external_request_id = user_payload.get("request_id") or external_request_id
            for item in user_payload["items"]:
                user_identity = item.get("user_id") or item.get("open_id")
                if not user_identity:
                    continue
                user_identity = str(user_identity)
                existing_user = users_by_identity.get(user_identity)
                if existing_user is None:
                    users_by_identity[user_identity] = _feishu_user_record(item)
                    continue

                existing_department_ids = existing_user.get("department_ids") or []
                merged_department_ids = dict.fromkeys([*existing_department_ids, *(item.get("department_ids") or [])])
                existing_user["department_ids"] = [str(value) for value in merged_department_ids]
                for key, value in {**_feishu_profile(item), **_feishu_custom_fields(item)}.items():
                    if value and not existing_user.get(key):
                        existing_user[key] = value

        user_list = [item for item in users_by_identity.values() if item.get("user_id") or item.get("open_id")]

        return CapabilityExecutionResult.success_result(
            f"Feishu user sync payload fetched for source '{getattr(source, 'name', '')}'",
            payload={
                "group_list": group_list,
                "user_list": user_list,
                "external_request_id": external_request_id,
            },
        )
