from ldap3.core.exceptions import LDAPBindError

from apps.system_mgmt.providers.log import logger
from apps.system_mgmt.providers.base import BaseLoginAuthAdapter
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult

from . import client


class ADLoginAuthAdapter(BaseLoginAuthAdapter):
    capability_key = "login_auth"

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

        binding = kwargs.get("binding")
        external_match_field = str(getattr(binding, "external_field", "") or "").strip()
        attributes = list(
            dict.fromkeys(attribute for attribute in [identity_field, external_match_field, "distinguishedName"] if attribute)
        )

        try:
            connection_config = client.build_connection_config(config)
            user = client.search_single_user(connection_config, identity_field, username, attributes)
            if not user:
                return CapabilityExecutionResult.failed_result(
                    "AD user not found",
                    code="provider.auth_failed",
                    field=identity_field,
                )

            distinguished_name = client.get_ldap_scalar(user.get("distinguishedName"))
            if not distinguished_name:
                return CapabilityExecutionResult.failed_result(
                    "AD user distinguishedName is missing",
                    code="provider.invalid_response",
                    field="distinguishedName",
                )

            client.bind_user_dn(connection_config, distinguished_name, password)
        except ValueError as error:
            return CapabilityExecutionResult.failed_result(
                f"AD login_auth configuration error: {error}",
                code="provider.invalid_config",
                field=identity_field,
            )
        except LDAPBindError as error:
            if "invalidcredentials" in str(error).lower():
                return CapabilityExecutionResult.failed_result(
                    "AD authentication failed",
                    code="provider.auth_failed",
                    field=identity_field,
                )
            logger.debug(f"AD authenticate bind failed: error_type={type(error).__name__}")
            return CapabilityExecutionResult.failed_result(
                "AD authentication failed",
                code="provider.auth_failed",
                field=identity_field,
            )
        except Exception as error:
            logger.debug(f"AD authenticate failed: error_type={type(error).__name__}")
            return CapabilityExecutionResult.failed_result(
                "AD authentication failed",
                code="provider.auth_failed",
                field=identity_field,
            )

        external_user = {
            "sAMAccountName": client.get_ldap_scalar(user.get("sAMAccountName")),
            "userPrincipalName": client.get_ldap_scalar(user.get("userPrincipalName")),
            "name": client.get_ldap_scalar(user.get("displayName")) or client.get_ldap_scalar(user.get("sAMAccountName")) or username,
            "email": client.get_ldap_scalar(user.get("mail")),
            "mobile": (
                client.get_ldap_scalar(user.get("mobile"))
                or client.get_ldap_scalar(user.get("telephoneNumber"))
                or client.get_ldap_scalar(user.get("mobilePhone"))
            ),
            "distinguishedName": distinguished_name,
        }
        if external_match_field:
            external_user[external_match_field] = client.get_ldap_scalar(user.get(external_match_field))

        return CapabilityExecutionResult.success_result(
            "AD login authenticated",
            payload={
                "external_user": external_user
            },
        )
