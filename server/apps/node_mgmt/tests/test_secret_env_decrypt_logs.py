"""解密失败日志不得写入异常正文或 Sidecar 上报 payload。"""

import logging
from types import SimpleNamespace

import pytest

from apps.node_mgmt.nats import node as node_nats
from apps.node_mgmt.services.sidecar import Sidecar

pytestmark = pytest.mark.unit


def test_cloud_region_secret_decrypt_log_omits_exception_body(mocker, caplog):
    sentinel = "SENTINEL_DEC_5953_ZzQ9mK2p"
    env = SimpleNamespace(type="secret", key="NATS_PASSWORD", value="cipher")
    mocker.patch("apps.node_mgmt.nats.node.SidecarEnv.objects.filter", return_value=[env])
    mocker.patch.object(node_nats.AESCryptor, "decode", side_effect=ValueError(sentinel))

    with caplog.at_level(logging.WARNING, logger="node"):
        out = node_nats.get_cloud_region_envconfig("1")

    assert out["NATS_PASSWORD"] == "cipher"
    assert sentinel not in caplog.text
    assert "error_type=ValueError" in caplog.text


def test_sidecar_update_debug_does_not_log_request_data():
    import inspect

    source = inspect.getsource(Sidecar.update_node_client)
    assert "node data:" not in source
    assert "field_count=%s" in source
