# -*- coding: utf-8 -*-
"""PCNodeParams 下发合同测试。

锁定 PC 任务（model_id=pc, driver_type=job）的节点参数：
- Windows 固定 WinRM 参数透传（scheme/transport/cert_validation/port）；
- macOS SSH 密码与私钥两种认证的占位符与 env_config 透传；
- 秘密值只进 env_config，不以明文进 headers；
- 多凭据池按既有 flatten 约定下发。
"""
import json
import types

from apps.cmdb.constants.constants import CollectDriverTypes
from apps.cmdb.node_configs.config_factory import NodeParamsFactory


def _fake_task(credential, params, timeout=120):
    task = types.SimpleNamespace()
    task.id = 321
    task.model_id = "pc"
    task.driver_type = CollectDriverTypes.JOB
    task.timeout = timeout
    task.decrypt_credentials = credential
    task.instances = []
    task.ip_range = "192.168.1.56"
    task.params = params
    task.access_point = [{"id": "node-1"}]
    return task


WINDOWS_PARAMS = {
    "os_type": "windows",
    "winrm_scheme": "https",
    "winrm_transport": "ntlm",
    "winrm_cert_validation": False,
}

MACOS_PARAMS = {"os_type": "macos"}


def test_factory_resolves_pc_node_params():
    cls = NodeParamsFactory.get_params_class("pc", CollectDriverTypes.JOB)
    assert cls.supported_model_id == "pc"
    assert cls.plugin_name == "pc_info"


def test_pc_node_params_windows_contract():
    task = _fake_task(
        credential={"username": "ACME\\alice", "password": "secret", "port": 5986},
        params=WINDOWS_PARAMS,
    )
    node = NodeParamsFactory.get_node_params(task)
    headers = node.custom_headers()

    assert headers["cmdbplugin_name"] == "pc_info"
    assert headers["cmdbmodel_id"] == "pc"
    assert headers["cmdbexecutor_type"] == "job"
    assert headers["cmdbos_type"] == "windows"
    assert headers["cmdbport"] == "5986"
    assert headers["cmdbwinrm_scheme"] == "https"
    assert headers["cmdbwinrm_transport"] == "ntlm"
    assert headers["cmdbwinrm_cert_validation"] == "False"
    # 秘密只以占位符下发，真实值在 env_config
    assert headers["cmdbpassword"] == "${PASSWORD_password_cmdb_321}"
    assert node.env_config() == {"PASSWORD_password_cmdb_321": "secret"}
    assert "secret" not in json.dumps(headers, ensure_ascii=False)


def test_pc_node_params_macos_password_contract():
    task = _fake_task(
        credential={"username": "admin", "password": "secret", "port": 22},
        params=MACOS_PARAMS,
    )
    node = NodeParamsFactory.get_node_params(task)
    headers = node.custom_headers()

    assert headers["cmdbos_type"] == "macos"
    assert headers["cmdbport"] == "22"
    assert headers["cmdbusername"] == "admin"
    assert headers["cmdbpassword"] == "${PASSWORD_password_cmdb_321}"
    # macOS 密码认证不下发 WinRM 参数
    assert "cmdbwinrm_scheme" not in headers
    assert node.env_config() == {"PASSWORD_password_cmdb_321": "secret"}


def test_pc_node_params_macos_private_key_contract():
    task = _fake_task(
        credential={"username": "admin", "private_key": "PEM-DATA", "passphrase": "pp", "port": 22},
        params=MACOS_PARAMS,
    )
    node = NodeParamsFactory.get_node_params(task)
    headers = node.custom_headers()

    assert headers["cmdbprivate_key"] == "${PRIVATEKEY_private_key_cmdb_321}"
    assert headers["cmdbpassphrase"] == "${PASSPHRASE_passphrase_cmdb_321}"
    assert "cmdbpassword" not in headers
    env = node.env_config()
    assert env["PRIVATEKEY_private_key_cmdb_321"] == "PEM-DATA"
    assert env["PASSPHRASE_passphrase_cmdb_321"] == "pp"
    dumped = json.dumps(headers, ensure_ascii=False)
    assert "PEM-DATA" not in dumped
    assert "pp" not in dumped


def test_pc_node_params_credentials_pool_flattened():
    task = _fake_task(
        credential=[
            {"credential_id": "cred_a", "username": "u1", "password": "p1", "port": 5986},
            {"credential_id": "cred_b", "username": "u2", "password": "p2", "port": 5986},
        ],
        params=WINDOWS_PARAMS,
    )
    node = NodeParamsFactory.get_node_params(task)
    headers = node.custom_headers()

    assert headers["cmdbcredential_count"] == "2"
    assert headers["cmdbcredential_0_username"] == "u1"
    assert headers["cmdbcredential_0_password"] == "${PASSWORD_password_cmdb_321_0}"
    assert headers["cmdbcredential_0_credential_id"] == "cred_a"
    assert headers["cmdbcredential_1_username"] == "u2"
    assert headers["cmdbcredential_1_password"] == "${PASSWORD_password_cmdb_321_1}"
    env = node.env_config()
    assert env["PASSWORD_password_cmdb_321_0"] == "p1"
    assert env["PASSWORD_password_cmdb_321_1"] == "p2"
    assert "p1" not in json.dumps(headers, ensure_ascii=False)
