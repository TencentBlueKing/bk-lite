from dataclasses import replace
from unittest.mock import patch

import pytest
from ldap3.core.exceptions import LDAPBindError

from apps.system_mgmt.providers.adapters.ad import ADLoginAuthAdapter, ADUserSyncAdapter
from apps.system_mgmt.providers.adapters.common.ldap import build_connection_config, resolve_ldap_server_target


pytestmark = pytest.mark.unit


def _base_config():
    return {
        "connection_url": "ad.example.com",
        "ssl_encryption": "none",
        "timeout": 10,
        "bind_dn": "CN=svc,OU=Service,DC=corp,DC=example,DC=com",
        "bind_password": "secret",
        "base_dn": "DC=corp,DC=example,DC=com",
        "login_auth_identity_field": "sAMAccountName",
    }


@patch("apps.system_mgmt.providers.adapters.ad.bind_user_dn")
@patch("apps.system_mgmt.providers.adapters.ad.search_single_user")
def test_ad_login_auth_searches_single_user_and_binds_password(mock_search_single_user, mock_bind_user_dn):
    mock_search_single_user.return_value = {
        "sAMAccountName": "alice",
        "displayName": "Alice",
        "mail": "alice@example.com",
        "telephoneNumber": "13800000000",
        "distinguishedName": "CN=Alice,OU=Users,DC=corp,DC=example,DC=com",
    }

    result = ADLoginAuthAdapter.authenticate(
        config=_base_config(),
        provider_key="ad",
        capability_key="login_auth",
        username="alice",
        password="secret",
    )

    assert result.success is True
    assert result.payload["external_user"]["sAMAccountName"] == "alice"
    mock_search_single_user.assert_called_once()
    mock_bind_user_dn.assert_called_once()


@patch("apps.system_mgmt.providers.adapters.ad.bind_user_dn")
@patch("apps.system_mgmt.providers.adapters.ad.search_single_user")
def test_ad_login_auth_unwraps_single_value_lists(mock_search_single_user, mock_bind_user_dn):
    mock_search_single_user.return_value = {
        "sAMAccountName": ["alice"],
        "displayName": ["Alice"],
        "mail": ["alice@example.com"],
        "telephoneNumber": ["13800000000"],
        "distinguishedName": ["CN=Alice,OU=Users,DC=corp,DC=example,DC=com"],
    }

    result = ADLoginAuthAdapter.authenticate(
        config=_base_config(),
        provider_key="ad",
        capability_key="login_auth",
        username="alice",
        password="secret",
    )

    assert result.success is True
    assert result.payload["external_user"]["sAMAccountName"] == "alice"
    mock_bind_user_dn.assert_called_once_with(
        mock_bind_user_dn.call_args.args[0],
        "CN=Alice,OU=Users,DC=corp,DC=example,DC=com",
        "secret",
    )


@patch("apps.system_mgmt.providers.adapters.ad.search_single_user")
def test_ad_login_auth_fails_when_search_returns_multiple_users(mock_search_single_user):
    mock_search_single_user.side_effect = ValueError("multiple")

    result = ADLoginAuthAdapter.authenticate(
        config=_base_config(),
        provider_key="ad",
        capability_key="login_auth",
        username="alice",
        password="secret",
    )

    assert result.success is False
    # 多匹配也是配置/数据问题，走 provider.invalid_config + 消息含原始 error
    assert result.errors[0].code == "provider.invalid_config"
    assert "multiple" in result.errors[0].message


@patch("apps.system_mgmt.providers.adapters.ad.search_single_user")
def test_ad_login_auth_fails_when_user_not_found(mock_search_single_user):
    mock_search_single_user.return_value = None

    result = ADLoginAuthAdapter.authenticate(
        config=_base_config(),
        provider_key="ad",
        capability_key="login_auth",
        username="alice",
        password="secret",
    )

    assert result.success is False
    assert result.errors[0].field == "sAMAccountName"


@patch("apps.system_mgmt.providers.adapters.ad.logger")
@patch("apps.system_mgmt.providers.adapters.ad.bind_user_dn")
@patch("apps.system_mgmt.providers.adapters.ad.search_single_user")
def test_ad_login_auth_invalid_credentials_are_treated_as_auth_failure_without_exception_log(
    mock_search_single_user,
    mock_bind_user_dn,
    mock_logger,
):
    mock_search_single_user.return_value = {
        "sAMAccountName": "alice",
        "displayName": "Alice",
        "distinguishedName": "CN=Alice,OU=Users,DC=corp,DC=example,DC=com",
    }
    mock_bind_user_dn.side_effect = LDAPBindError("automatic bind not successful - invalidCredentials")

    result = ADLoginAuthAdapter.authenticate(
        config=_base_config(),
        provider_key="ad",
        capability_key="login_auth",
        username="alice",
        password="wrong-password",
    )

    assert result.success is False
    assert result.errors[0].code == "provider.auth_failed"
    mock_logger.exception.assert_not_called()


@patch("apps.system_mgmt.providers.adapters.ad.search_entries")
def test_ad_user_sync_returns_payload_compatible_with_existing_field_mapping(mock_search_entries):
    mock_search_entries.side_effect = [
        [
            {
                "sAMAccountName": "alice",
                "userPrincipalName": "alice@corp.example.com",
                "displayName": "Alice",
                "mail": "alice@example.com",
                "telephoneNumber": "13800000000",
                "distinguishedName": "CN=Alice,OU=Dev,OU=PAAS,DC=corp,DC=example,DC=com",
            }
        ],
        [
            {"distinguishedName": "OU=PAAS,DC=corp,DC=example,DC=com"},
            {"distinguishedName": "OU=Dev,OU=PAAS,DC=corp,DC=example,DC=com"},
        ],
    ]

    result = ADUserSyncAdapter.sync_users(
        config=_base_config(),
        provider_key="ad",
        capability_key="user_sync",
        source=type(
            "Source",
            (),
            {
                "business_config": {
                    "root_dn": "OU=PAAS,DC=corp,DC=example,DC=com",
                    "user_object_class": "user",
                    "user_filter": "(&(objectCategory=Person)(sAMAccountName=*))",
                    "organization_object_class": "organizationalUnit",
                }
            },
        )(),
    )

    assert result.success is True
    assert result.payload["user_list"][0]["sAMAccountName"] == "alice"
    assert result.payload["user_list"][0]["department_ids"] == ["OU=Dev,OU=PAAS,DC=corp,DC=example,DC=com"]
    assert result.payload["group_list"] == [
        {
            "id": "OU=Dev,OU=PAAS,DC=corp,DC=example,DC=com",
            "name": "Dev",
            "parent_id": "OU=PAAS,DC=corp,DC=example,DC=com",
        }
    ]
    assert mock_search_entries.call_count == 2
    assert mock_search_entries.call_args_list[0].args[2] == "(&(objectClass=user)(&(objectCategory=Person)(sAMAccountName=*)))"
    assert mock_search_entries.call_args_list[1].args[2] == "(objectClass=organizationalUnit)"


@patch("apps.system_mgmt.providers.adapters.ad.search_entries")
def test_ad_user_sync_uses_default_directory_query_parameters(mock_search_entries):
    mock_search_entries.side_effect = [[], []]

    result = ADUserSyncAdapter.sync_users(
        config=_base_config(),
        provider_key="ad",
        capability_key="user_sync",
        source=type("Source", (), {"business_config": {"root_dn": "OU=PAAS,DC=corp,DC=example,DC=com"}})(),
    )

    assert result.success is True
    assert mock_search_entries.call_args_list[0].args[2] == "(&(objectClass=user)(&(objectCategory=Person)(sAMAccountName=*)))"
    assert mock_search_entries.call_args_list[1].args[2] == "(objectClass=organizationalUnit)"


def test_ad_user_sync_requires_root_dn():
    result = ADUserSyncAdapter.sync_users(
        config=_base_config(),
        provider_key="ad",
        capability_key="user_sync",
        source=type("Source", (), {"business_config": {}})(),
    )

    assert result.success is False
    assert result.errors[0].field == "root_dn"


@patch("apps.system_mgmt.providers.adapters.ad.probe_root_dse")
def test_ad_connection_tests_use_root_dse_probe(mock_probe_root_dse):
    login_result = ADLoginAuthAdapter.test_connection(
        config=_base_config(),
        provider_key="ad",
        capability_key="login_auth",
    )
    sync_result = ADUserSyncAdapter.test_connection(
        config=_base_config(),
        provider_key="ad",
        capability_key="user_sync",
    )

    assert login_result.success is True
    assert sync_result.success is True
    assert mock_probe_root_dse.call_count == 2


@patch("apps.system_mgmt.providers.adapters.ad.probe_root_dse")
@patch("apps.system_mgmt.providers.adapters.ad.build_connection_config")
def test_ad_user_sync_test_connection_succeeds_without_base_dn(
    mock_build_connection_config,
    mock_probe_root_dse,
):
    def _build(config):
        return replace(build_connection_config(config), base_dn="")

    mock_build_connection_config.side_effect = _build

    result = ADUserSyncAdapter.test_connection(
        config=_base_config(),
        provider_key="ad",
        capability_key="user_sync",
    )

    assert result.success is True


@patch("apps.system_mgmt.providers.adapters.ad.probe_root_dse")
@patch("apps.system_mgmt.providers.adapters.ad.build_connection_config")
def test_ad_login_auth_test_connection_succeeds_without_base_dn(
    mock_build_connection_config,
    mock_probe_root_dse,
):
    def _build(config):
        return replace(build_connection_config(config), base_dn="")

    mock_build_connection_config.side_effect = _build

    result = ADLoginAuthAdapter.test_connection(
        config=_base_config(),
        provider_key="ad",
        capability_key="login_auth",
    )

    assert result.success is True


def test_resolve_ldap_server_target_supports_ip_only_input():
    assert resolve_ldap_server_target("10.10.248.33", use_ssl=False) == ("10.10.248.33", 389)
    assert resolve_ldap_server_target("10.10.248.33", use_ssl=True) == ("10.10.248.33", 636)


def test_resolve_ldap_server_target_keeps_backward_compatible_url_parsing():
    assert resolve_ldap_server_target("ldap://10.10.248.33:1389", use_ssl=False) == ("10.10.248.33", 1389)
    assert resolve_ldap_server_target("10.10.248.33:2389", use_ssl=False) == ("10.10.248.33", 2389)


@pytest.mark.parametrize(
    "config",
    [
        {},                                       # 完全缺省
        {"base_dn": ""},                          # 空字符串
        {"base_dn": None},                        # None
        {"base_dn": "   "},                       # 仅空白
        {"connection_url": "x"},                  # 缺 base_dn 但有其它字段
    ],
)
def test_build_connection_config_raises_when_base_dn_missing(config):
    with pytest.raises(ValueError, match=r"base_dn"):
        build_connection_config(config)


def test_build_connection_config_does_not_silently_default_missing_base_dn_to_empty():
    """回归锁：之前实现 ``str(raw.get('base_dn') or '')`` 在缺省时静默返回 base_dn='',
    空串传到 ldap3 search_base='' 会搜不到任何 user，触发迷惑的 'AD user not found'。
    新实现必须在缺省 / None / 空串 / 空白时立即抛 ValueError，不允许静默降级。
    """
    from dataclasses import asdict

    # 验证：缺省 / None / 空串 三种「曾经的静默路径」现在都抛 ValueError
    for silent_config in [{}, {"base_dn": None}, {"base_dn": ""}]:
        with pytest.raises(ValueError):
            build_connection_config(silent_config)

    # 验证：非空 base_dn 不抛，且 LDAPConnectionConfig.base_dn 等于传入值（不被改写）
    config = build_connection_config({"base_dn": "DC=corp,DC=com", "connection_url": "x"})
    assert asdict(config)["base_dn"] == "DC=corp,DC=com"
    # 验证：纯空白也被识别为空（strip 后等于空）
    with pytest.raises(ValueError):
        build_connection_config({"base_dn": "   "})


def test_ad_authenticate_returns_invalid_config_when_base_dn_missing():
    """base_dn 缺失时 authenticate 不应返回迷惑的 'AD user not found'，
    而应明确返回 provider.invalid_config + 含 base_dn 的消息。"""
    result = ADLoginAuthAdapter.authenticate(
        config={},   # 完全没填 base_dn
        provider_key="ad",
        capability_key="login_auth",
        username="alice",
        password="secret",
    )

    assert result.success is False
    assert result.errors[0].code == "provider.invalid_config"
    assert "base_dn" in result.errors[0].message.lower()
