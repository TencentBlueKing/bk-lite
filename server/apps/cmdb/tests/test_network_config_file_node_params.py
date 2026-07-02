from types import SimpleNamespace

from apps.cmdb.node_configs.network_config_file import NetworkConfigFileNodeParams


def _task():
    return SimpleNamespace(
        id=42,
        model_id="network_config_file",
        driver_type="protocol",
        timeout=30,
        params={
            "config_name": "running-config",
            "commands": "show running-config\nshow version",
            "need_enable": True,
        },
        instances=[
            {
                "_id": "101",
                "model_id": "switch",
                "inst_name": "10.0.0.1-switch",
                "ip_addr": "10.0.0.1",
                "brand": "Cisco",
                "device_type": "cisco_ios",
            }
        ],
        ip_range="",
        access_point=[{"id": 9}],
        decrypt_credentials={
            "username": "admin",
            "password": "secret",
            "enable_password": "enable-secret",
            "port": 2222,
        },
    )


def test_need_enable_is_derived_from_credential_enable_password():
    task = _task()
    task.params["need_enable"] = False
    params = NetworkConfigFileNodeParams(task)

    headers = params.custom_headers()
    env = params.env_config()

    assert headers["cmdbneed_enable"] == "True"
    assert headers["cmdbenable_password"].startswith("${PASSWORD_enable_password_cmdb_42")
    assert any(value == "enable-secret" for value in env.values())


def test_need_enable_is_false_without_credential_enable_password():
    task = _task()
    task.params["need_enable"] = True
    task.decrypt_credentials.pop("enable_password")
    params = NetworkConfigFileNodeParams(task)

    headers = params.custom_headers()
    env = params.env_config()

    assert headers["cmdbneed_enable"] == "False"
    assert "cmdbenable_password" not in headers
    assert not any(value == "enable-secret" for value in env.values())


def test_custom_headers_include_network_config_callback_and_device_type():
    params = NetworkConfigFileNodeParams(_task())

    headers = params.custom_headers()

    assert headers["cmdbplugin_name"] == "network_config_file_info"
    assert headers["cmdbmodel_id"] == "network_config_file"
    assert headers["cmdbtarget_model_id"] == "switch"
    assert headers["cmdbtarget_instance_id"] == "101"
    assert headers["cmdbdevice_type"] == "cisco_ios"
    assert headers["cmdbcallback_subject"] == "receive_config_file_result"
    assert headers["cmdbconfig_name"] == "running-config"
    assert headers["cmdbcommands"] == "show running-config\nshow version"


def test_env_config_contains_password_and_enable_password_without_plain_headers():
    params = NetworkConfigFileNodeParams(_task())

    headers = params.custom_headers()
    env = params.env_config()

    assert headers["cmdbpassword"].startswith("${PASSWORD_password_cmdb_42")
    assert headers["cmdbenable_password"].startswith("${PASSWORD_enable_password_cmdb_42")
    assert "secret" not in headers.values()
    assert "enable-secret" not in headers.values()
    assert any(value == "secret" for value in env.values())
    assert any(value == "enable-secret" for value in env.values())
