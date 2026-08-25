"""本包厂商请求层：LDAP bind/search 与连接失败映射。能力模块经本模块访问目录，不要再抄一份。"""

import re

from ldap3.core.exceptions import LDAPBindError

from apps.system_mgmt.providers.common.ldap import (
    LDAPSearchError,
    bind_user_dn,
    build_connection_config,
    get_ldap_scalar,
    probe_root_dse,
    search_entries,
    search_single_user,
)
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult

LDAP_NO_SUCH_OBJECT = 32
LDAP_REFERRAL = 10
LDAP_INVALID_DN_SYNTAX = 34


def _build_ad_search_failure(error: LDAPSearchError) -> CapabilityExecutionResult:
    search_base = error.search_base
    missing_base = error.result_code in {LDAP_NO_SUCH_OBJECT, LDAP_REFERRAL, LDAP_INVALID_DN_SYNTAX}
    if missing_base:
        return CapabilityExecutionResult.failed_result(
            f"AD pull DN was not found: {search_base}",
            code="provider.invalid_config",
            field="root_dns",
            detail=search_base,
            external_code=str(error.result_code),
        )
    return CapabilityExecutionResult.failed_result(
        "AD user sync request failed",
        code="provider.request_failed",
        field="root_dns",
        detail=search_base,
        external_code=str(error.result_code),
    )


def _get_ldap_result_code(error: Exception) -> str:
    """Extract an LDAP result code without exposing the raw server response."""
    match = re.search(r"(?:ldap\s+)?result\s+(\d+)|-\s*(\d+)(?:\s*-|$)", str(error), re.IGNORECASE)
    if match is None:
        return ""
    return match.group(1) or match.group(2) or ""


def _build_ad_connection_failure(error: Exception) -> CapabilityExecutionResult:
    if isinstance(error, LDAPBindError):
        return CapabilityExecutionResult.failed_result(
            "AD connection credentials were rejected",
            code="provider.auth_failed",
            detail="LDAP bind rejected the configured credentials",
            external_code=_get_ldap_result_code(error),
        )

    return CapabilityExecutionResult.failed_result(
        "AD connection test failed",
        code="provider.request_failed",
        detail="LDAP connection request failed",
    )
