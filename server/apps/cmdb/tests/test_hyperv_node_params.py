# -*- coding: utf-8 -*-
"""HypervNodeParams 下发合同。

锁定 hyperv_host / job：
- 插件名 hyperv_info，执行器 job，接入点 node_id 与目标 hosts；
- WinRM 端口、scheme、transport、证书校验进入 headers；
- 缺省连接是 HTTP/5985/NTLM，证书校验关闭；
- 密码只以占位符进入 headers，明文只在 env_config。
"""
import json
import types

from apps.cmdb.constants.constants import CollectDriverTypes
from apps.cmdb.node_configs.config_factory import NodeParamsFactory


def _fake_task(credential, params, *, instances=None, ip_range="10.1.1.8"):
    task = types.SimpleNamespace()
    task.id = 321
    task.model_id = "hyperv_host"
    task.driver_type = CollectDriverTypes.JOB
    task.task_type = "vm"
    task.timeout = 180
    task.decrypt_credentials = credential
    task.instances = instances or []
    task.ip_range = ip_range
    task.params = params
    task.access_point = [{"id": "node-1", "cloud_region": 2}]
    return task


def test_factory_resolves_hyperv_node_params():
    cls = NodeParamsFactory.get_params_class("hyperv_host", CollectDriverTypes.JOB)
    assert cls.supported_model_id == "hyperv_host"
    assert cls.plugin_name == "hyperv_info"
    assert cls.supported_driver_type == CollectDriverTypes.JOB


def test_hyperv_node_params_default_winrm_contract():
    task = _fake_task(
        credential={"username": "administrator", "password": "hyperv-secret", "port": 5985},
        params={},
    )
    node = NodeParamsFactory.get_node_params(task)
    headers = node.custom_headers()

    assert headers["cmdbplugin_name"] == "hyperv_info"
    assert headers["cmdbmodel_id"] == "hyperv_host"
    assert headers["cmdbexecutor_type"] == "job"
    assert headers["cmdbnode_id"] == "node-1"
    assert headers["cmdbhosts"] == "10.1.1.8"
    assert headers["cmdbport"] == "5985"
    assert headers["cmdbwinrm_scheme"] == "http"
    assert headers["cmdbwinrm_transport"] == "ntlm"
    assert headers["cmdbwinrm_cert_validation"] == "False"
    assert headers["cmdbusername"] == "administrator"
    assert headers["cmdbpassword"] == "${PASSWORD_password_cmdb_321}"
    assert node.env_config() == {"PASSWORD_password_cmdb_321": "hyperv-secret"}
    assert "hyperv-secret" not in json.dumps(headers, ensure_ascii=False)


def test_hyperv_node_params_https_and_selected_hosts():
    task = _fake_task(
        credential={"username": "ACME\\alice", "password": "hyperv-secret", "port": 5986},
        params={
            "winrm_scheme": "https",
            "winrm_transport": "ntlm",
            "winrm_cert_validation": True,
            "target_source": "host",
        },
        instances=[{"ip_addr": "10.1.1.8"}, {"ip_addr": "10.1.1.9"}],
        ip_range="",
    )
    node = NodeParamsFactory.get_node_params(task)
    headers = node.custom_headers()

    assert headers["cmdbhosts"] == "10.1.1.8,10.1.1.9"
    assert headers["cmdbport"] == "5986"
    assert headers["cmdbwinrm_scheme"] == "https"
    assert headers["cmdbwinrm_cert_validation"] == "True"
    assert headers["cmdbpassword"] == "${PASSWORD_password_cmdb_321}"
    assert "hyperv-secret" not in json.dumps(headers, ensure_ascii=False)


def test_hyperv_node_params_credentials_pool_keeps_secrets_out_of_headers():
    task = _fake_task(
        credential=[
            {"credential_id": "cred_a", "username": "u1", "password": "p1", "port": 5985},
            {"credential_id": "cred_b", "username": "u2", "password": "p2", "port": 5985},
        ],
        params={"winrm_scheme": "http", "winrm_transport": "ntlm", "winrm_cert_validation": False},
    )
    node = NodeParamsFactory.get_node_params(task)
    headers = node.custom_headers()

    assert headers["cmdbcredential_count"] == "2"
    assert headers["cmdbcredential_0_node_id"] == "node-1"
    assert headers["cmdbcredential_0_port"] == "5985"
    assert headers["cmdbcredential_0_winrm_scheme"] == "http"
    assert headers["cmdbcredential_0_password"] == "${PASSWORD_password_cmdb_321_0}"
    assert headers["cmdbcredential_1_password"] == "${PASSWORD_password_cmdb_321_1}"
    assert node.env_config() == {
        "PASSWORD_password_cmdb_321_0": "p1",
        "PASSWORD_password_cmdb_321_1": "p2",
    }
    dumped = json.dumps(headers, ensure_ascii=False)
    assert "p1" not in dumped
    assert "p2" not in dumped
