from apps.system_mgmt.providers.log import logger
from apps.system_mgmt.providers.base import BaseUserSyncAdapter
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult
from apps.system_mgmt.services.ad_pull_dns import (
    AD_ROOT_DNS_FIELD,
    is_ad_multi_pull,
    normalize_ad_pull_dns,
    resolve_ad_local_root_scope_id,
)

from . import client


def _get_sync_user_attributes(source) -> list[str]:
    """仅查询当前同步源映射字段及构建组织关系必需的 DN。"""
    field_mapping = getattr(source, "field_mapping", None) or {}
    mapped_attributes = [str(attribute).strip() for attribute in field_mapping.values() if str(attribute or "").strip()]
    return list(dict.fromkeys([*mapped_attributes, "distinguishedName"]))


class ADUserSyncAdapter(BaseUserSyncAdapter):
    capability_key = "user_sync"
    DEFAULT_USER_OBJECT_CLASS = "user"
    DEFAULT_USER_FILTER = "(&(objectCategory=Person)(sAMAccountName=*))"
    DEFAULT_ORGANIZATION_OBJECT_CLASS = "organizationalUnit"

    @classmethod
    def test_connection(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        try:
            connection_config = client.build_connection_config(config)
            if not all(
                [
                    connection_config.connection_url,
                    connection_config.bind_dn,
                    connection_config.bind_password,
                ]
            ):
                return CapabilityExecutionResult.failed_result(
                    "AD connection configuration is incomplete",
                    code="provider.invalid_config",
                )

            client.probe_root_dse(connection_config)
        except Exception as error:
            return client._build_ad_connection_failure(error)

        return CapabilityExecutionResult.success_result("AD user sync capability is ready")

    @classmethod
    def sync_users(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        source = kwargs.get("source")
        business_config = getattr(source, "business_config", None) or {}
        pull_dns = normalize_ad_pull_dns(business_config)
        if not pull_dns:
            return CapabilityExecutionResult.failed_result(
                "AD user sync root DN is required",
                code="provider.invalid_config",
                field=AD_ROOT_DNS_FIELD,
            )

        local_root_scope_id = resolve_ad_local_root_scope_id(pull_dns)
        multi_pull = is_ad_multi_pull(pull_dns)

        user_object_class = cls._get_business_config_value(
            business_config,
            "user_object_class",
            cls.DEFAULT_USER_OBJECT_CLASS,
        )
        user_filter = cls._get_business_config_value(
            business_config,
            "user_filter",
            cls.DEFAULT_USER_FILTER,
        )
        organization_object_class = cls._get_business_config_value(
            business_config,
            "organization_object_class",
            cls.DEFAULT_ORGANIZATION_OBJECT_CLASS,
        )

        try:
            connection_config = client.build_connection_config(config)
            if not all(
                [
                    connection_config.connection_url,
                    connection_config.bind_dn,
                    connection_config.bind_password,
                ]
            ):
                return CapabilityExecutionResult.failed_result(
                    "AD connection configuration is incomplete",
                    code="provider.invalid_config",
                )

            user_filter_str = cls._build_object_search_filter(user_object_class, user_filter)
            org_filter_str = cls._build_object_class_filter(organization_object_class)
            user_attributes = _get_sync_user_attributes(source)

            user_entries: list[dict] = []
            organization_entries: list[dict] = []
            for pull_dn in pull_dns:
                user_entries.extend(
                    client.search_entries(
                        connection_config,
                        pull_dn,
                        user_filter_str,
                        user_attributes,
                        paged_size=100,
                    )
                )
                organization_entries.extend(
                    client.search_entries(
                        connection_config,
                        pull_dn,
                        org_filter_str,
                        ["distinguishedName"],
                        paged_size=100,
                    )
                )
        except Exception as error:
            logger.debug(f"AD user sync failed: error_type={type(error).__name__}")
            return CapabilityExecutionResult.failed_result(
                "AD user sync request failed",
                code="provider.request_failed",
            )

        group_map: dict[str, dict] = {}
        users_by_dn: dict[str, dict] = {}

        for user_entry in user_entries:
            normalized_user = cls._normalize_sync_user(user_entry)
            distinguished_name = normalized_user["distinguishedName"]
            if not distinguished_name:
                continue

            pull_dn = cls._match_pull_dn(distinguished_name, pull_dns)
            if not pull_dn:
                continue

            department_ids = cls._collect_department_dns(distinguished_name, pull_dn)
            if not department_ids:
                department_ids = [pull_dn]
            normalized_user["department_ids"] = department_ids
            users_by_dn[distinguished_name.lower()] = normalized_user

            for group_entry in cls._build_group_entries(
                department_ids,
                pull_dn,
                local_root_scope_id=local_root_scope_id,
                multi_pull=multi_pull,
            ):
                group_map[group_entry["id"].lower()] = group_entry

        for group_entry in cls._build_organization_group_entries(
            organization_entries,
            pull_dns,
            local_root_scope_id=local_root_scope_id,
            multi_pull=multi_pull,
        ):
            group_map[group_entry["id"].lower()] = group_entry

        if multi_pull:
            known_ids = {item["id"].lower() for item in group_map.values()}
            pull_dn_keys = {item.lower() for item in pull_dns}
            for group_entry in group_map.values():
                parent_id = str(group_entry.get("parent_id") or "")
                parent_key = parent_id.lower()
                if parent_key in pull_dn_keys and parent_key not in known_ids:
                    group_entry["parent_id"] = local_root_scope_id

        user_list = list(users_by_dn.values())
        group_list = sorted(group_map.values(), key=lambda item: (item["parent_id"], item["id"]))
        return CapabilityExecutionResult.success_result(
            "AD user sync payload prepared",
            payload={
                "group_list": group_list,
                "user_list": user_list,
                "local_root_scope_id": local_root_scope_id,
            },
        )

    @staticmethod
    def _get_business_config_value(business_config: dict, key: str, default: str) -> str:
        return str((business_config or {}).get(key) or default).strip() or default

    @staticmethod
    def _build_object_class_filter(object_class: str) -> str:
        return f"(objectClass={object_class})"

    @classmethod
    def _build_object_search_filter(cls, object_class: str, raw_filter: str) -> str:
        normalized_filter = str(raw_filter or "").strip() or cls.DEFAULT_USER_FILTER
        return f"(&{cls._build_object_class_filter(object_class)}{normalized_filter})"

    @staticmethod
    def _normalize_sync_user(user_entry: dict) -> dict:
        return {
            "sAMAccountName": client.get_ldap_scalar(user_entry.get("sAMAccountName")),
            "userPrincipalName": client.get_ldap_scalar(user_entry.get("userPrincipalName")),
            "displayName": client.get_ldap_scalar(user_entry.get("displayName")) or client.get_ldap_scalar(user_entry.get("sAMAccountName")),
            "mail": client.get_ldap_scalar(user_entry.get("mail")),
            "telephoneNumber": client.get_ldap_scalar(user_entry.get("telephoneNumber")),
            "mobile": client.get_ldap_scalar(user_entry.get("mobile")),
            "mobilePhone": client.get_ldap_scalar(user_entry.get("mobilePhone")),
            "distinguishedName": client.get_ldap_scalar(user_entry.get("distinguishedName")),
        }

    @classmethod
    def _match_pull_dn(cls, entry_dn: str, pull_dns: list[str]) -> str | None:
        entry_lower = entry_dn.strip().lower()
        # Prefer the longest matching pull DN (most specific).
        matches = []
        for pull_dn in pull_dns:
            pull_lower = pull_dn.lower()
            if entry_lower == pull_lower or entry_lower.endswith("," + pull_lower):
                matches.append(pull_dn)
        if not matches:
            return None
        return max(matches, key=len)

    @classmethod
    def _build_group_entries(
        cls,
        department_dns: list[str],
        pull_dn: str,
        *,
        local_root_scope_id: str,
        multi_pull: bool,
    ) -> list[dict]:
        group_list = []
        for department_dn in department_dns:
            if not multi_pull and department_dn.lower() == pull_dn.lower():
                continue
            parent_dn = cls._resolve_parent_department_dn(
                department_dn,
                pull_dn,
                local_root_scope_id=local_root_scope_id,
                multi_pull=multi_pull,
            )
            group_list.append(
                {
                    "id": department_dn,
                    "name": cls._get_rdn_value(department_dn),
                    "parent_id": parent_dn,
                }
            )
        return group_list

    @classmethod
    def _build_organization_group_entries(
        cls,
        organization_entries: list[dict],
        pull_dns: list[str],
        *,
        local_root_scope_id: str,
        multi_pull: bool,
    ) -> list[dict]:
        group_list = []
        for entry in organization_entries:
            department_dn = client.get_ldap_scalar(entry.get("distinguishedName"))
            if not department_dn:
                continue
            pull_dn = cls._match_pull_dn(department_dn, pull_dns)
            if not pull_dn:
                continue
            if not multi_pull and department_dn.lower() == pull_dn.lower():
                continue
            group_list.append(
                {
                    "id": department_dn,
                    "name": cls._get_rdn_value(department_dn),
                    "parent_id": cls._resolve_parent_department_dn(
                        department_dn,
                        pull_dn,
                        local_root_scope_id=local_root_scope_id,
                        multi_pull=multi_pull,
                    ),
                }
            )
        return group_list

    @classmethod
    def _collect_department_dns(cls, user_dn: str, root_dn: str) -> list[str]:
        root_dn_normalized = root_dn.strip()
        user_dn_normalized = user_dn.strip()
        if not user_dn_normalized or not root_dn_normalized:
            return []

        user_dn_lower = user_dn_normalized.lower()
        root_dn_lower = root_dn_normalized.lower()
        if user_dn_lower == root_dn_lower:
            return [root_dn_normalized]
        if not user_dn_lower.endswith(root_dn_lower):
            return [root_dn_normalized]

        relative_dn = user_dn_normalized[: len(user_dn_normalized) - len(root_dn_normalized)].rstrip(",")
        if not relative_dn:
            return [root_dn_normalized]

        rdns = [item.strip() for item in relative_dn.split(",") if item.strip()]
        department_dns = []
        suffix = root_dn_normalized
        for rdn in reversed(rdns):
            if not cls._is_department_rdn(rdn):
                continue
            suffix = f"{rdn},{suffix}"
            department_dns.append(suffix)
        return department_dns or [root_dn_normalized]

    @classmethod
    def _resolve_parent_department_dn(
        cls,
        department_dn: str,
        pull_dn: str,
        *,
        local_root_scope_id: str,
        multi_pull: bool,
    ) -> str:
        normalized_department_dn = department_dn.strip()
        normalized_pull_dn = pull_dn.strip()
        if normalized_department_dn.lower() == normalized_pull_dn.lower():
            return local_root_scope_id if multi_pull else normalized_pull_dn

        parts = [item.strip() for item in normalized_department_dn.split(",") if item.strip()]
        if len(parts) <= 1:
            return local_root_scope_id if multi_pull else normalized_pull_dn

        parent_dn = ",".join(parts[1:])
        parent_lower = parent_dn.lower()
        pull_lower = normalized_pull_dn.lower()
        if parent_lower == pull_lower or parent_lower.endswith("," + pull_lower) or parent_lower.endswith(pull_lower):
            return parent_dn
        return local_root_scope_id if multi_pull else normalized_pull_dn

    @staticmethod
    def _is_department_rdn(rdn: str) -> bool:
        return str(rdn).lower().startswith(("ou=", "dc=", "o="))

    @staticmethod
    def _get_rdn_value(distinguished_name: str) -> str:
        first_part = str(distinguished_name or "").split(",", 1)[0].strip()
        if "=" not in first_part:
            return first_part
        return first_part.split("=", 1)[1]
