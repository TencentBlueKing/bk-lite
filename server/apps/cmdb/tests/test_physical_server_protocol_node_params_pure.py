from types import SimpleNamespace

import pytest

from apps.cmdb.constants.constants import CollectDriverTypes
from apps.cmdb.node_configs.config_factory import NodeParamsFactory

pytestmark = pytest.mark.unit


def _task(collection_protocol, credential):
    return SimpleNamespace(
        id=42,
        model_id="physcial_server",
        driver_type=CollectDriverTypes.PROTOCOL,
        decrypt_credentials=credential,
        timeout=30,
        params={"collection_protocol": collection_protocol},
        instances=[
            {
                "_id": "physical-1",
                "model_id": "physcial_server",
                "inst_name": "10.0.0.8",
                "ip_addr": "10.0.0.8",
            }
        ],
        ip_range="",
        access_point=[{"id": "node-1"}],
        cycle_value_type="cycle",
        cycle_value=5,
    )


def test_ipmi_protocol_headers_keep_legacy_defaults():
    node = NodeParamsFactory.get_node_params(
        _task(
            "ipmi",
            {
                "username": "admin",
                "password": "secret",
                "port": 623,
                "privilege": "administrator",
            },
        )
    )

    headers = node.custom_headers()

    assert headers["cmdbcollection_protocol"] == "ipmi"
    assert headers["cmdbpreflight_kind"] == "snmp"
    assert headers["cmdbpreflight_kind_explicit"] == "True"
    assert headers["cmdbport"] == "623"


def test_redfish_protocol_defers_endpoint_checks_to_each_credential():
    node = NodeParamsFactory.get_node_params(
        _task(
            "redfish",
            {
                "username": "Administrator",
                "password": "secret",
                "port": 443,
            },
        )
    )

    headers = node.custom_headers()

    assert headers["cmdbcollection_protocol"] == "redfish"
    assert headers["cmdbpreflight_kind"] == "none"
    assert headers["cmdbpreflight_kind_explicit"] == "True"
    assert headers["cmdbrotate_on_credential_failure"] == "True"
    assert headers["cmdbssl"] == "True"
    assert headers["cmdbverify_tls"] == "True"
    assert headers["cmdbport"] == "443"


def test_redfish_protocol_headers_allow_explicitly_disabling_tls_verification():
    node = NodeParamsFactory.get_node_params(
        _task(
            "redfish",
            {
                "username": "Administrator",
                "password": "secret",
                "port": 443,
                "verify_tls": False,
            },
        )
    )

    headers = node.custom_headers()

    assert headers["cmdbverify_tls"] == "False"


def test_redfish_protocol_headers_publish_every_credential_in_order():
    node = NodeParamsFactory.get_node_params(
        _task(
            "redfish",
            [
                {
                    "credential_id": "cred-1",
                    "credential_version": 2,
                    "username": "Administrator",
                    "password": "first-secret",
                    "port": 443,
                    "verify_tls": True,
                },
                {
                    "credential_id": "cred-2",
                    "credential_version": 1,
                    "username": "readonly",
                    "password": "second-secret",
                    "port": 8443,
                    "verify_tls": False,
                },
            ],
        )
    )

    headers = node.custom_headers()

    assert headers["cmdbcollection_protocol"] == "redfish"
    assert headers["cmdbpreflight_kind"] == "none"
    assert "cmdbport" not in headers
    assert headers["cmdbrotate_on_credential_failure"] == "True"
    assert headers["cmdbcredential_count"] == "2"
    assert headers["cmdbcredential_0_credential_id"] == "cred-1"
    assert headers["cmdbcredential_0_credential_version"] == "2"
    assert headers["cmdbcredential_0_username"] == "Administrator"
    assert headers["cmdbcredential_0_password"] == "${PASSWORD_password_cmdb_42_0}"
    assert headers["cmdbcredential_0_port"] == "443"
    assert headers["cmdbcredential_0_verify_tls"] == "True"
    assert headers["cmdbcredential_1_username"] == "readonly"
    assert headers["cmdbcredential_1_password"] == "${PASSWORD_password_cmdb_42_1}"
    assert headers["cmdbcredential_1_port"] == "8443"
    assert headers["cmdbcredential_1_verify_tls"] == "False"
    assert node.env_config() == {
        "PASSWORD_password_cmdb_42_0": "first-secret",
        "PASSWORD_password_cmdb_42_1": "second-secret",
    }


def test_ipmi_protocol_headers_publish_every_credential_in_order():
    node = NodeParamsFactory.get_node_params(
        _task(
            "ipmi",
            [
                {
                    "credential_id": "cred-1",
                    "username": "operator",
                    "password": "first-secret",
                    "port": 623,
                    "privilege": "operator",
                },
                {
                    "credential_id": "cred-2",
                    "username": "administrator",
                    "password": "second-secret",
                    "port": 9623,
                    "privilege": "administrator",
                },
            ],
        )
    )

    headers = node.custom_headers()

    assert headers["cmdbcollection_protocol"] == "ipmi"
    assert headers["cmdbpreflight_kind"] == "snmp"
    assert headers["cmdbport"] == "623"
    assert headers["cmdbcredential_count"] == "2"
    assert headers["cmdbcredential_0_privilege"] == "operator"
    assert headers["cmdbcredential_1_port"] == "9623"
    assert headers["cmdbcredential_1_privilege"] == "administrator"
