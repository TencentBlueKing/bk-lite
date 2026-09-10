from types import SimpleNamespace

import pytest

from apps.cmdb.node_configs.config_factory import NodeParamsFactory


def _fake_instance(model_id, credential, instance):
    return SimpleNamespace(
        id=321,
        model_id=model_id,
        driver_type="protocol",
        timeout=60,
        decrypt_credentials=[credential],
        instances=[instance],
        params={},
        access_point=[{"id": "node-1"}],
        ip_range="",
    )


@pytest.mark.parametrize(
    "model_id,plugin_name,default_port,instance",
    [
        (
            "fusioninsight",
            "fusioninsight_info",
            443,
            {"endpoint": "https://fi.example.com:9443/web"},
        ),
        (
            "storage",
            "oceanstor_info",
            8088,
            {"ip_addr": "10.0.0.88"},
        ),
        (
            "dell_unity",
            "dell_unity_info",
            443,
            {"ip_addr": "10.0.0.20"},
        ),
        (
            "netapp_ontap",
            "netapp_ontap_info",
            443,
            {"ip_addr": "10.0.0.10"},
        ),
    ],
)
def test_platform_api_credentials_match_collector_contract(
    model_id,
    plugin_name,
    default_port,
    instance,
):
    task = _fake_instance(
        model_id,
        {
            "username": "collector",
            "password": "secret",
            "port": default_port,
            "verify_tls": False,
        },
        instance,
    )

    node = NodeParamsFactory.get_node_params(task)
    headers = node.custom_headers()

    assert headers["cmdbplugin_name"] == plugin_name
    assert headers["cmdbusername"] == "${PASSWORD_username_cmdb_321}"
    assert headers["cmdbpassword"] == "${PASSWORD_password_cmdb_321}"
    assert headers["cmdbport"] == str(default_port)
    assert headers["cmdbscheme"] == "https"
    assert headers["cmdbverify_tls"] == "False"
    expected_host = {
        "fusioninsight": "fi.example.com",
        "storage": "10.0.0.88",
        "dell_unity": "10.0.0.20",
        "netapp_ontap": "10.0.0.10",
    }[model_id]
    assert headers["cmdbhost"] == expected_host
    assert node.env_config() == {
        "PASSWORD_username_cmdb_321": "collector",
        "PASSWORD_password_cmdb_321": "secret",
    }


def test_fusioninsight_legacy_aksk_still_runs_until_task_is_resaved():
    task = _fake_instance(
        "fusioninsight",
        {
            "accessKey": "legacy-user",
            "accessSecret": "legacy-secret",
        },
        {"endpoint": "https://fi.example.com"},
    )

    node = NodeParamsFactory.get_node_params(task)

    assert node.env_config() == {
        "PASSWORD_username_cmdb_321": "legacy-user",
        "PASSWORD_password_cmdb_321": "legacy-secret",
    }


def test_platform_api_legacy_credential_uses_endpoint_scheme_and_custom_port():
    task = _fake_instance(
        "fusioninsight",
        {
            "username": "collector",
            "password": "secret",
        },
        {"endpoint": "https://fi.example.com:9443/web"},
    )

    headers = NodeParamsFactory.get_node_params(task).custom_headers()

    assert headers["cmdbhost"] == "fi.example.com"
    assert headers["cmdbscheme"] == "https"
    assert headers["cmdbport"] == "9443"
