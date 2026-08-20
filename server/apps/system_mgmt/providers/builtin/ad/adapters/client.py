"""本包厂商请求层：LDAP bind/search 与连接失败映射。能力模块经本模块访问目录，不要再抄一份。"""

import re

from ldap3.core.exceptions import LDAPBindError

from apps.system_mgmt.providers.common.ldap import (
    bind_user_dn,
    build_connection_config,
    get_ldap_scalar,
    probe_root_dse,
    search_entries,
    search_single_user,
)
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult

def _get_ldap_result_code(error: Exception) -> str:
    """Extract an LDAP result code without exposing the raw server response."""
    match = re.search(r"(?:ldap\s+)?result\s+(\d+)|-\s*(\d+)\s*-", str(error), re.IGNORECASE)
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
