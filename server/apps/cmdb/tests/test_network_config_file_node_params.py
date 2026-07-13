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


# ---------------------------------------------------------------------------
# P2-2.2 — get_hosts 不再对每个 instance 重复 resolve_brand
# ---------------------------------------------------------------------------

class TestGetHostsSkipsBrandResolution:
    """P2-2.2: get_hosts 之前对每个 instance 跑 normalize(其中 resolve_device_type
    查 brand 字典),N 个 instance 重复 N 次。get_hosts 不需要 device_type,
    只抽 host 即可,brand 解析只在 set_credential 里发生 1 次。"""

    def test_get_hosts_skips_brand_resolution_for_each_instance(self, monkeypatch):
        """N 个 instance 时,resolve_brand 应只在 set_credential 调 1 次。"""
        from apps.cmdb.services import network_config_file_policy
        from apps.cmdb.node_configs import network_config_file as nc_module

        task = _task()
        task.instances = [
            {"_id": "1", "model_id": "switch", "brand": "Cisco", "ip_addr": "10.0.0.1"},
            {"_id": "2", "model_id": "switch", "brand": "Cisco", "ip_addr": "10.0.0.2"},
            {"_id": "3", "model_id": "switch", "brand": "Cisco", "ip_addr": "10.0.0.3"},
        ]

        resolve_call_count = [0]
        original_resolve = network_config_file_policy.resolve_device_type

        def counting_resolve(brand):
            resolve_call_count[0] += 1
            return original_resolve(brand)

        # patch 两个引用点:policy 模块本身 + node_config 端
        monkeypatch.setattr(network_config_file_policy, "resolve_device_type", counting_resolve)
        monkeypatch.setattr(nc_module, "resolve_device_type", counting_resolve, raising=False)

        params = NetworkConfigFileNodeParams(task)
        _ = params.custom_headers()  # 触发 set_credential 一次
        _ = params.env_config()

        # 3 个 instance:get_hosts 不应触发 resolve_brand,set_credential 只调一次
        assert resolve_call_count[0] <= 1, (
            f"resolve_brand 应只在 set_credential 触发 1 次,实际 {resolve_call_count[0]} 次"
        )
