from unittest.mock import MagicMock, patch

import pytest

from apps.system_mgmt.providers.common.ldap import (
    LDAPConnectionConfig,
    LDAPSearchError,
    create_service_connection,
    search_entries,
)


pytestmark = pytest.mark.unit

LDAP3_STUB = (None, "BASE", None, "SUBTREE", None, None)


def _config():
    return LDAPConnectionConfig(
        connection_url="ad.example.com",
        use_ssl=False,
        timeout=10,
        bind_dn="CN=svc,DC=corp,DC=example,DC=com",
        bind_password="secret",
        base_dn="DC=corp,DC=example,DC=com",
    )


def _connection(*, result_code: int, entries=None, description=""):
    connection = MagicMock()
    connection.entries = entries or []
    connection.result = {
        "result": result_code,
        "description": description,
        "dn": "DC=corp,DC=example,DC=com",
        "message": "0000208D: NameErr: DSID-03100241 bind_dn=CN=svc,...",
        "controls": {},
    }
    return connection


@patch("apps.system_mgmt.providers.common.ldap._load_ldap3")
def test_create_service_connection_disables_referral_chasing(mock_load_ldap3):
    connection_cls = MagicMock()
    server_cls = MagicMock()
    mock_load_ldap3.return_value = (None, None, None, None, connection_cls, server_cls)

    create_service_connection(_config())

    assert connection_cls.call_args.kwargs["auto_referrals"] is False


@patch("apps.system_mgmt.providers.common.ldap._load_ldap3", return_value=LDAP3_STUB)
@patch("apps.system_mgmt.providers.common.ldap.create_service_connection")
def test_search_entries_raises_on_no_such_object(mock_connect, _mock_ldap3):
    search_base = "OU=missing,DC=corp,DC=example,DC=com"
    mock_connect.return_value = _connection(result_code=32, description="noSuchObject")

    with pytest.raises(LDAPSearchError) as exc_info:
        search_entries(_config(), search_base, "(objectClass=*)")

    error = exc_info.value
    assert error.result_code == 32
    assert error.search_base == search_base
    assert "private" not in str(error)
    assert "bind_dn" not in str(error)
    assert "0000208D" not in str(error)
    assert "NameErr" not in str(error)


@patch("apps.system_mgmt.providers.common.ldap._load_ldap3", return_value=LDAP3_STUB)
@patch("apps.system_mgmt.providers.common.ldap.create_service_connection")
def test_search_entries_empty_success_is_not_missing_object(mock_connect, _mock_ldap3):
    mock_connect.return_value = _connection(result_code=0, description="success")

    results = search_entries(_config(), "OU=empty,DC=corp,DC=example,DC=com", "(objectClass=*)")

    assert results == []


@patch("apps.system_mgmt.providers.common.ldap._load_ldap3", return_value=LDAP3_STUB)
@patch("apps.system_mgmt.providers.common.ldap.create_service_connection")
def test_search_entries_paged_raises_on_no_such_object(mock_connect, _mock_ldap3):
    search_base = "OU=missing,DC=corp,DC=example,DC=com"
    mock_connect.return_value = _connection(result_code=32, description="noSuchObject")

    with pytest.raises(LDAPSearchError) as exc_info:
        search_entries(_config(), search_base, "(objectClass=*)", paged_size=100)

    assert exc_info.value.result_code == 32
    assert exc_info.value.search_base == search_base

@patch("apps.system_mgmt.providers.common.ldap._load_ldap3", return_value=LDAP3_STUB)
@patch("apps.system_mgmt.providers.common.ldap.create_service_connection")
def test_search_entries_preserves_search_base_when_referral_chase_raises(mock_connect, _mock_ldap3):
    search_base = "OU=yhd,DC=bktest,DC=com,DC=1"
    connection = _connection(result_code=10, description="referral")
    connection.search.side_effect = RuntimeError("referral chase failed")
    mock_connect.return_value = connection

    with pytest.raises(LDAPSearchError) as exc_info:
        search_entries(_config(), search_base, "(objectClass=*)")

    assert exc_info.value.result_code == 10
    assert exc_info.value.search_base == search_base