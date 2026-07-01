# -*- coding: utf-8 -*-
"""私有云采集下发链路（NodeParams）测试：补齐后 5 朵云均可解析并下发，
不再抛 ValueError；下发参数键对齐各 stargazer 采集器读取的键。"""
import types
import pytest

from apps.cmdb.node_configs.config_factory import NodeParamsFactory

# 仅社区版 node_configs 实际注册的私有云（openstack/manageone/smartx 属企业插件，
# 本社区 worktree 未注册，get_params_class 会抛 ValueError，见
# test_unregistered_cloud_raises_valueerror）。
CLOUDS = {
    "hwcloud": "huaweicloud_info",
    "fusioninsight": "fusioninsight_info",
}

# 企业云：社区 worktree 未注册 node_configs，工厂应抛 ValueError。
ENTERPRISE_ONLY_CLOUDS = ["openstack", "manageone", "smartx"]


def _fake_instance(model_id, host_via="endpoint"):
    inst = types.SimpleNamespace()
    inst.id = 123
    inst.model_id = model_id
    inst.driver_type = "protocol"
    inst.timeout = 60
    inst.decrypt_credentials = {
        "accessKey": "AK-xxx",
        "accessSecret": "SK-yyy",
        "regions": {"resource_id": "cn-north-4", "resource_name": "华北"},
    }
    # host 两种来源：平台实例 endpoint 或 global_domain_name
    inst.instances = [{host_via: "https://cloud.example.com:8774"}]
    inst.params = {}
    inst.access_point = [{"id": "node-1"}]
    inst.ip_range = ""
    return inst


@pytest.mark.parametrize("model_id,plugin_name", list(CLOUDS.items()))
def test_factory_resolves_each_cloud_no_valueerror(model_id, plugin_name):
    # 修复前：get_params_class 对这些 model_id 抛 ValueError("不支持的 model_id")
    cls = NodeParamsFactory.get_params_class(model_id, "protocol")
    assert cls.supported_model_id == model_id
    assert cls.plugin_name == plugin_name


@pytest.mark.parametrize("model_id,plugin_name", list(CLOUDS.items()))
def test_push_params_builds_and_headers_align_collector(model_id, plugin_name):
    node = NodeParamsFactory.get_node_params(_fake_instance(model_id))
    # push_params 不再抛异常，结构完整
    nodes = node.main("push")
    assert len(nodes) == 1
    n = nodes[0]
    assert n["id"] == "cmdb_123" and n["type"] == model_id and n["node_id"] == "node-1"
    assert n["collect_type"] == "http"

    headers = node.custom_headers()
    # 凭据经环境变量引用下发（不落明文）
    assert headers["cmdbaccessKey"] == "${PASSWORD_access_key_cmdb_123}"
    assert headers["cmdbaccessSecret"] == "${PASSWORD_access_secret_cmdb_123}"
    # region 来自凭据 regions.resource_id
    assert headers["cmdbregion"] == "cn-north-4"
    # host 以 'host' 键下发（采集器读 params.get('host')）
    assert headers["cmdbhost"] == "https://cloud.example.com:8774"
    # 插件名 / model_id 正确
    assert headers["cmdbplugin_name"] == plugin_name
    assert headers["cmdbmodel_id"] == model_id

    # 环境变量携带真实密钥
    env = node.env_config()
    assert env["PASSWORD_access_key_cmdb_123"] == "AK-xxx"
    assert env["PASSWORD_access_secret_cmdb_123"] == "SK-yyy"


@pytest.mark.parametrize("model_id", ENTERPRISE_ONLY_CLOUDS)
def test_unregistered_cloud_raises_valueerror(model_id):
    """社区 worktree 未注册 openstack/manageone/smartx 的 NodeParams，工厂应抛 ValueError。"""
    with pytest.raises(ValueError):
        NodeParamsFactory.get_params_class(model_id, "protocol")


def test_host_falls_back_to_global_domain_name():
    """实例属性是 global_domain_name（无 endpoint）时，host 取 global_domain_name。"""
    node = NodeParamsFactory.get_node_params(_fake_instance("hwcloud", host_via="global_domain_name"))
    assert node.custom_headers()["cmdbhost"] == "https://cloud.example.com:8774"


def test_project_id_pushed_when_credential_has_it():
    """华为云需 project_id：凭据捕获到才下发（不臆造）；下发键为 'project_id'。"""
    inst = _fake_instance("hwcloud")
    inst.decrypt_credentials = {**inst.decrypt_credentials, "project_id": "p-abc"}
    node = NodeParamsFactory.get_node_params(inst)
    assert node.custom_headers()["cmdbproject_id"] == "p-abc"


def test_project_id_absent_not_pushed():
    node = NodeParamsFactory.get_node_params(_fake_instance("hwcloud"))
    assert "cmdbproject_id" not in node.custom_headers()


def test_host_prefers_task_params_host():
    inst = _fake_instance("hwcloud")
    inst.params = {"host": "https://from-params.example.com"}
    node = NodeParamsFactory.get_node_params(inst)
    assert node.custom_headers()["cmdbhost"] == "https://from-params.example.com"
