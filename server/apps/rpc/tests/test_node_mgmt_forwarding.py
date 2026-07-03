"""rpc.node_mgmt.NodeMgmt 转发契约测试。

NodeMgmt 构造时按 is_local_client 选 AppClient（本地）或 RpcClient（NATS）。
本测试构造 NATS 形态（默认），随后把 self.client / self.permission_client
替换为记录器，断言方法名 + 参数原样转发。能抓方法名/参数顺序回归。
不触达真实 NATS。
"""
import pydantic.root_model  # noqa

import pytest

from apps.rpc.node_mgmt import NodeMgmt

pytestmark = pytest.mark.unit


class _Recorder:
    def __init__(self):
        self.calls = []

    def run(self, method_name, *args, **kwargs):
        self.calls.append((method_name, args, kwargs))
        return {"result": True}


@pytest.fixture
def node(monkeypatch):
    # 强制走 NATS 形态（is_local_client=False），避免动态 import node_mgmt.nats
    monkeypatch.setenv("IS_LOCAL_RPC", "0")
    n = NodeMgmt(is_local_client=False)
    n.client = _Recorder()
    n.permission_client = _Recorder()
    return n


def _last(rec):
    return rec.calls[-1]


def test_get_module_data_走permission_client(node):
    node.get_module_data(module="m", page=1)
    assert _last(node.permission_client) == ("get_node_module_data", (), {"module": "m", "page": 1})
    assert node.client.calls == []


def test_get_module_list_走permission_client(node):
    node.get_module_list(module="m")
    assert _last(node.permission_client) == ("get_node_module_list", (), {"module": "m"})


def test_cloud_region_list_走client(node):
    node.cloud_region_list()
    assert _last(node.client) == ("cloud_region_list", (), {})


def test_get_cloud_region_proxy_address_位置参数(node):
    node.get_cloud_region_proxy_address(1, ["1", "2"])
    assert _last(node.client) == ("get_cloud_region_proxy_address", (1, ["1", "2"]), {})


def test_get_cloud_region_proxy_address_默认organization_ids为None(node):
    node.get_cloud_region_proxy_address(2)
    assert _last(node.client) == ("get_cloud_region_proxy_address", (2, None), {})


def test_node_list_转发query_data(node):
    q = {"cloud_region_id": 1, "page": 1}
    node.node_list(q)
    assert _last(node.client) == ("node_list", (q,), {})


def test_get_node_names_by_ids_转发(node):
    node.get_node_names_by_ids(["a", "b"])
    assert _last(node.client) == ("get_node_names_by_ids", (["a", "b"],), {})


def test_get_nodes_by_ids_转发(node):
    node.get_nodes_by_ids(["x"])
    assert _last(node.client) == ("get_nodes_by_ids", (["x"],), {})


def test_batch_create_configs_and_child_configs_两个列表(node):
    node.batch_create_configs_and_child_configs([{"a": 1}], [{"b": 2}])
    assert _last(node.client) == ("batch_create_configs_and_child_configs", ([{"a": 1}], [{"b": 2}]), {})


def test_batch_add_node_child_config_转发(node):
    node.batch_add_node_child_config([{"id": 1}])
    assert _last(node.client) == ("batch_add_node_child_config", ([{"id": 1}],), {})


def test_batch_add_node_config_转发(node):
    node.batch_add_node_config([{"id": 2}])
    assert _last(node.client) == ("batch_add_node_config", ([{"id": 2}],), {})


def test_get_child_configs_by_ids_转发(node):
    node.get_child_configs_by_ids([1, 2])
    assert _last(node.client) == ("get_child_configs_by_ids", ([1, 2],), {})


def test_get_configs_by_ids_转发(node):
    node.get_configs_by_ids([3])
    assert _last(node.client) == ("get_configs_by_ids", ([3],), {})


def test_get_authorized_nodes_by_ids_默认permission_data为空字典(node):
    node.get_authorized_nodes_by_ids(["n1"])
    assert _last(node.client) == ("get_authorized_nodes_by_ids", (["n1"], {}), {})


def test_get_authorized_nodes_by_ids_带permission_data(node):
    node.get_authorized_nodes_by_ids(["n1"], {"team": [1]})
    assert _last(node.client) == ("get_authorized_nodes_by_ids", (["n1"], {"team": [1]}), {})


def test_update_child_config_content_组装字典(node):
    node.update_child_config_content(7, "content", {"K": "V"})
    assert _last(node.client) == (
        "update_child_config_content",
        ({"id": 7, "content": "content", "env_config": {"K": "V"}},),
        {},
    )


def test_update_config_content_默认env_config为None(node):
    node.update_config_content(8, "ctt")
    assert _last(node.client) == (
        "update_config_content",
        ({"id": 8, "content": "ctt", "env_config": None},),
        {},
    )


def test_delete_child_configs_转发(node):
    node.delete_child_configs([1])
    assert _last(node.client) == ("delete_child_configs", ([1],), {})


def test_delete_configs_转发(node):
    node.delete_configs([2])
    assert _last(node.client) == ("delete_configs", ([2],), {})


def test_collectors_import_方法名为import_collectors(node):
    node.collectors_import([{"name": "c"}])
    assert _last(node.client) == ("import_collectors", ([{"name": "c"}],), {})


def test_cloudregion_tls_env_by_node_id_转发(node):
    node.cloudregion_tls_env_by_node_id("nid")
    assert _last(node.client) == ("cloudregion_tls_env_by_node_id", ("nid",), {})


def test_get_cloud_region_envconfig_转发(node):
    node.get_cloud_region_envconfig(5)
    assert _last(node.client) == ("get_cloud_region_envconfig", (5,), {})


def test_install_collector_组装字典(node):
    node.install_collector(3, ["n1", "n2"])
    assert _last(node.client) == ("install_collector", ({"collector_package": 3, "nodes": ["n1", "n2"]},), {})


def test_install_managed_component_组装字典(node):
    node.install_managed_component(4, ["n3"])
    assert _last(node.client) == ("install_managed_component", ({"collector_package": 4, "nodes": ["n3"]},), {})


def test_local_client_使用appclient路径(monkeypatch):
    """is_local_client=True 时应绑定到 node_mgmt.nats 本地 AppClient。"""
    monkeypatch.setenv("IS_LOCAL_RPC", "0")
    n = NodeMgmt(is_local_client=True)
    assert n.client.path == "apps.node_mgmt.nats.node"
    assert n.permission_client.path == "apps.node_mgmt.nats.node.permission"


def test_env_变量强制本地模式(monkeypatch):
    """IS_LOCAL_RPC=1 即使显式传 False 也走本地。"""
    monkeypatch.setenv("IS_LOCAL_RPC", "1")
    n = NodeMgmt(is_local_client=False)
    assert n.client.path == "apps.node_mgmt.nats.node"
