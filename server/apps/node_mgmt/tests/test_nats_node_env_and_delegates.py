"""节点 NATS：TLS 环境、云区域列表/环境变量，以及委托入口。"""
from unittest.mock import patch

import pytest

from apps.node_mgmt.constants.database import EnvVariableConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import CloudRegion, Node, SidecarEnv
from apps.node_mgmt.nats import node as n

pytestmark = pytest.mark.django_db


def _region(name):
    return CloudRegion.objects.create(name=name, introduction="", created_by="tester", updated_by="tester")


def test_cloudregion_tls_env_defaults_when_node_missing():
    assert n.cloudregion_tls_env_by_node_id("missing-node-881") == {
        "NATS_PROTOCOL": "nats",
        "NATS_TLS_CA_FILE": "",
        "NATS_TLS_CA_WIN_FILE": "",
    }


def test_cloudregion_tls_env_overlays_sidecar_values():
    region = _region("tls-env-881")
    node = Node.objects.create(
        id="tls-node-881",
        name="tls-node-881",
        ip="10.8.8.1",
        operating_system=NodeConstants.LINUX_OS,
        collector_configuration_directory="/etc/collector",
        cloud_region=region,
        created_by="tester",
        updated_by="tester",
    )
    SidecarEnv.objects.create(cloud_region=region, key="NATS_PROTOCOL", value="tls", type=EnvVariableConstants.TYPE_NORMAL)
    SidecarEnv.objects.create(cloud_region=region, key="NATS_TLS_CA_FILE", value="/ca.pem", type=EnvVariableConstants.TYPE_NORMAL)
    out = n.cloudregion_tls_env_by_node_id(node.id)
    assert out["NATS_PROTOCOL"] == "tls"
    assert out["NATS_TLS_CA_FILE"] == "/ca.pem"
    assert out["NATS_TLS_CA_WIN_FILE"] == ""


def test_cloud_region_list_includes_created_region():
    region = _region("list-region-881")
    rows = n.cloud_region_list()
    assert {"id": region.id, "name": "list-region-881"} in rows


def test_get_cloud_region_envconfig_plain_and_secret_decode_fallback():
    region = _region("env-region-881")
    SidecarEnv.objects.create(cloud_region=region, key="PLAIN", value="visible", type=EnvVariableConstants.TYPE_NORMAL)
    SidecarEnv.objects.create(cloud_region=region, key="SECRET", value="cipher", type=EnvVariableConstants.TYPE_SECRET)
    with patch("apps.node_mgmt.nats.node.AESCryptor") as aes_cls:
        aes_cls.return_value.decode.side_effect = ValueError("bad-cipher")
        out = n.get_cloud_region_envconfig(str(region.id))
    assert out["PLAIN"] == "visible"
    assert out["SECRET"] == "cipher"


def test_collector_list_always_empty():
    assert n.collector_list({"page": 1}) == []


def test_nats_delegates_to_services():
    with patch.object(n.NodeService, "get_node_list", return_value={"count": 0, "nodes": []}) as listed:
        assert n.node_list({"name": "x", "page": 2, "page_size": 5}) == {"count": 0, "nodes": []}
        listed.assert_called_once()
        args = listed.call_args.args
        assert args[2] == "x"
        assert args[5] == 2
        assert args[6] == 5

    with patch.object(n.NodeService, "get_node_names_by_ids", return_value={"a": "n1"}) as names:
        assert n.get_node_names_by_ids(["a"]) == {"a": "n1"}
        names.assert_called_once_with(["a"])

    with patch.object(n.NodeService, "get_nodes_by_ids", return_value=[{"id": "a"}]) as nodes:
        assert n.get_nodes_by_ids(["a"]) == [{"id": "a"}]
        nodes.assert_called_once_with(["a"])

    with patch.object(n.NodeService, "get_authorized_nodes_by_ids", return_value=["n1"]) as auth:
        assert n.get_authorized_nodes_by_ids(["n1"], {"team": 1}) == ["n1"]
        auth.assert_called_once_with(["n1"], {"team": 1})

    with patch.object(n, "import_collector", return_value={"ok": True}) as imported:
        assert n.import_collectors([{"id": 1}]) == {"ok": True}
        imported.assert_called_once_with([{"id": 1}])

    svc = n.NatsService
    with patch.object(svc, "batch_create_configs_and_child_configs") as batch:
        n.batch_create_configs_and_child_configs([{"id": "c"}], [{"id": "ch"}])
        batch.assert_called_once_with([{"id": "c"}], [{"id": "ch"}])
    with patch.object(svc, "batch_create_child_configs") as child:
        n.batch_add_node_child_config([{"id": "ch"}])
        child.assert_called_once_with([{"id": "ch"}])
    with patch.object(svc, "batch_create_configs") as cfg:
        n.batch_add_node_config([{"id": "c"}])
        cfg.assert_called_once_with([{"id": "c"}])
    with patch.object(svc, "get_child_configs_by_ids", return_value=[{"id": 1}]) as gch:
        assert n.get_child_configs_by_ids([1]) == [{"id": 1}]
        gch.assert_called_once_with([1])
    with patch.object(svc, "get_configs_by_ids", return_value=[{"id": 2}]) as gcfg:
        assert n.get_configs_by_ids([2]) == [{"id": 2}]
        gcfg.assert_called_once_with([2])
    with patch.object(svc, "update_child_config_content") as uch:
        n.update_child_config_content({"id": 3, "content": "x", "env_config": {"a": 1}})
        uch.assert_called_once_with(3, "x", {"a": 1})
    with patch.object(svc, "update_config_content") as ucfg:
        n.update_config_content({"id": 4, "content": "y", "env_config": None})
        ucfg.assert_called_once_with(4, "y", None)
    with patch.object(svc, "delete_child_configs") as dch:
        n.delete_child_configs([5])
        dch.assert_called_once_with([5])
    with patch.object(svc, "delete_configs") as dcfg:
        n.delete_configs([6])
        dcfg.assert_called_once_with([6])


def test_install_collector_and_managed_component_return_task_id():
    with (
        patch.object(n.InstallerService, "install_collector", return_value="tid-881") as install,
        patch.object(n.install_collector_task, "delay") as delay,
    ):
        payload = {"collector_package": "pkg", "nodes": ["n1"]}
        assert n.install_collector(payload) == {"task_id": "tid-881"}
        assert n.install_managed_component(payload) == {"task_id": "tid-881"}
    assert install.call_count == 2
    assert delay.call_count == 2
    delay.assert_called_with("tid-881")


def test_update_config_content_requires_payload_and_existing_row():
    from apps.core.exceptions.base_app_exception import BaseAppException

    with pytest.raises(BaseAppException, match="must be provided"):
        n.NatsService().update_child_config_content(1, None, None)
    with pytest.raises(BaseAppException, match="not found"):
        n.NatsService().update_child_config_content(999881001, "x", None)
    with pytest.raises(BaseAppException, match="must be provided"):
        n.NatsService().update_config_content(1, None, None)
    with pytest.raises(BaseAppException, match="not found"):
        n.NatsService().update_config_content("missing-cfg-881", "x", None)
