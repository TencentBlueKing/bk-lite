from ldap3.core.exceptions import LDAPBindError

from apps.core.logger import logger
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult

from .base import BaseLoginAuthAdapter, BaseUserSyncAdapter
from .common.ldap import (
    bind_user_dn,
    build_connection_config,
    get_ldap_scalar,
    probe_root_dse,
    search_entries,
    search_single_user,
)


AD_LOGIN_ATTRIBUTES = [
    "sAMAccountName",
    "userPrincipalName",
    "displayName",
    "mail",
    "telephoneNumber",
    "distinguishedName",
]


class ADLoginAuthAdapter(BaseLoginAuthAdapter):
    capability_key = "login_auth"

    @classmethod
    def test_connection(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        try:
            connection_config = build_connection_config(config)
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

            probe_root_dse(connection_config)
        except Exception as error:
            logger.exception(f"AD login connection test failed: {error}")
            return CapabilityExecutionResult.failed_result(
                "AD login connection test failed",
                code="provider.request_failed",
            )

        return CapabilityExecutionResult.success_result("AD login capability is ready")

    @classmethod
    def authenticate(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        username = str(kwargs.get("username") or "").strip()
        password = kwargs.get("password") or ""
        if not username or not password:
            return CapabilityExecutionResult.failed_result(
                "AD login request is missing required parameters",
                code="provider.invalid_config",
                field="username" if not username else "password",
            )

        identity_field = str((config or {}).get("login_auth_identity_field") or "sAMAccountName").strip() or "sAMAccountName"
        if identity_field not in {"sAMAccountName", "userPrincipalName"}:
            return CapabilityExecutionResult.failed_result(
                "AD login identity field is invalid",
                code="provider.invalid_config",
                field="login_auth_identity_field",
            )

        try:
            connection_config = build_connection_config(config)
            user = search_single_user(connection_config, identity_field, username, AD_LOGIN_ATTRIBUTES)
            if not user:
                return CapabilityExecutionResult.failed_result(
                    "AD user not found",
                    code="provider.auth_failed",
                    field=identity_field,
                )

            distinguished_name = get_ldap_scalar(user.get("distinguishedName"))
            if not distinguished_name:
                return CapabilityExecutionResult.failed_result(
                    "AD user distinguishedName is missing",
                    code="provider.invalid_response",
                    field="distinguishedName",
                )

            bind_user_dn(connection_config, distinguished_name, password)
        except ValueError as error:
            return CapabilityExecutionResult.failed_result(
                f"AD login_auth configuration error: {error}",
                code="provider.invalid_config",
                field=identity_field,
            )
        except LDAPBindError as error:
            if "invalidcredentials" in str(error).lower():
                logger.warning("AD authentication failed due to invalid credentials")
                return CapabilityExecutionResult.failed_result(
                    "AD authentication failed",
                    code="provider.auth_failed",
                    field=identity_field,
                )
            logger.exception(f"AD authenticate bind failed: {error}")
            return CapabilityExecutionResult.failed_result(
                "AD authentication failed",
                code="provider.auth_failed",
                field=identity_field,
            )
        except Exception as error:
            logger.exception(f"AD authenticate failed: {error}")
            return CapabilityExecutionResult.failed_result(
                "AD authentication failed",
                code="provider.auth_failed",
                field=identity_field,
            )

        return CapabilityExecutionResult.success_result(
            "AD login authenticated",
            payload={
                "external_user": {
                    "sAMAccountName": get_ldap_scalar(user.get("sAMAccountName")),
                    "userPrincipalName": get_ldap_scalar(user.get("userPrincipalName")),
                    "name": get_ldap_scalar(user.get("displayName")) or get_ldap_scalar(user.get("sAMAccountName")) or username,
                    "email": get_ldap_scalar(user.get("mail")),
                    "mobile": get_ldap_scalar(user.get("telephoneNumber")),
                    "distinguishedName": distinguished_name,
                }
            },
        )


class ADUserSyncAdapter(BaseUserSyncAdapter):
    capability_key = "user_sync"
    DEFAULT_USER_OBJECT_CLASS = "user"
    DEFAULT_USER_FILTER = "(&(objectCategory=Person)(sAMAccountName=*))"
    DEFAULT_ORGANIZATION_OBJECT_CLASS = "organizationalUnit"

    @classmethod
    def test_connection(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        try:
            connection_config = build_connection_config(config)
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

            probe_root_dse(connection_config)
        except Exception as error:
            logger.exception(f"AD user sync connection test failed: {error}")
            return CapabilityExecutionResult.failed_result(
                "AD user sync connection test failed",
                code="provider.request_failed",
            )

        return CapabilityExecutionResult.success_result("AD user sync capability is ready")

    @classmethod
    def sync_users(cls, config: dict, provider_key: str, capability_key: str, **kwargs):
        source = kwargs.get("source")
        business_config = getattr(source, "business_config", None) or {}
        root_dn = str(business_config.get("root_dn") or "").strip()
        if not root_dn:
            return CapabilityExecutionResult.failed_result(
                "AD user sync root DN is required",
                code="provider.invalid_config",
                field="root_dn",
            )

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
            connection_config = build_connection_config(config)
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

            user_entries = search_entries(
                connection_config,
                root_dn,
                cls._build_object_search_filter(user_object_class, user_filter),
                AD_LOGIN_ATTRIBUTES,
                paged_size=100,
            )
            organization_entries = search_entries(
                connection_config,
                root_dn,
                cls._build_object_class_filter(organization_object_class),
                ["distinguishedName"],
                paged_size=100,
            )
        except Exception as error:
            logger.exception(f"AD user sync failed: {error}")
            return CapabilityExecutionResult.failed_result(
                "AD user sync request failed",
                code="provider.request_failed",
            )

        group_map: dict[str, dict] = {}
        user_list = []
        for user_entry in user_entries:
            normalized_user = cls._normalize_sync_user(user_entry)
            distinguished_name = normalized_user["distinguishedName"]
            if not distinguished_name:
                continue

            department_ids = cls._collect_department_dns(distinguished_name, root_dn)
            normalized_user["department_ids"] = department_ids or [root_dn]
            user_list.append(normalized_user)

            for group_entry in cls._build_group_entries(normalized_user["department_ids"], root_dn):
                group_map[group_entry["id"]] = group_entry

        for group_entry in cls._build_organization_group_entries(organization_entries, root_dn):
            group_map[group_entry["id"]] = group_entry

        group_list = sorted(group_map.values(), key=lambda item: (item["parent_id"], item["id"]))
        return CapabilityExecutionResult.success_result(
            "AD user sync payload prepared",
            payload={"group_list": group_list, "user_list": user_list},
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
            "sAMAccountName": get_ldap_scalar(user_entry.get("sAMAccountName")),
            "userPrincipalName": get_ldap_scalar(user_entry.get("userPrincipalName")),
            "displayName": get_ldap_scalar(user_entry.get("displayName")) or get_ldap_scalar(user_entry.get("sAMAccountName")),
            "mail": get_ldap_scalar(user_entry.get("mail")),
            "telephoneNumber": get_ldap_scalar(user_entry.get("telephoneNumber")),
            "distinguishedName": get_ldap_scalar(user_entry.get("distinguishedName")),
        }

    @classmethod
    def _build_group_entries(cls, department_dns: list[str], root_dn: str) -> list[dict]:
        group_list = []
        for department_dn in department_dns:
            if department_dn == root_dn:
                continue
            parent_dn = cls._resolve_parent_department_dn(department_dn, root_dn)
            group_list.append(
                {
                    "id": department_dn,
                    "name": cls._get_rdn_value(department_dn),
                    "parent_id": parent_dn,
                }
            )
        return group_list

    @classmethod
    def _build_organization_group_entries(cls, organization_entries: list[dict], root_dn: str) -> list[dict]:
        group_list = []
        for entry in organization_entries:
            department_dn = get_ldap_scalar(entry.get("distinguishedName"))
            if not department_dn or department_dn == root_dn:
                continue
            group_list.append(
                {
                    "id": department_dn,
                    "name": cls._get_rdn_value(department_dn),
                    "parent_id": cls._resolve_parent_department_dn(department_dn, root_dn),
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
    def _resolve_parent_department_dn(cls, department_dn: str, root_dn: str) -> str:
        normalized_department_dn = department_dn.strip()
        normalized_root_dn = root_dn.strip()
        if normalized_department_dn == normalized_root_dn:
            return normalized_root_dn

        parts = [item.strip() for item in normalized_department_dn.split(",") if item.strip()]
        if len(parts) <= 1:
            return normalized_root_dn

        parent_dn = ",".join(parts[1:])
        return parent_dn if parent_dn.lower().endswith(normalized_root_dn.lower()) else normalized_root_dn

    @staticmethod
    def _is_department_rdn(rdn: str) -> bool:
        return str(rdn).lower().startswith(("ou=", "dc=", "o="))

    @staticmethod
    def _get_rdn_value(distinguished_name: str) -> str:
        first_part = str(distinguished_name or "").split(",", 1)[0].strip()
        if "=" not in first_part:
            return first_part
        return first_part.split("=", 1)[1]
