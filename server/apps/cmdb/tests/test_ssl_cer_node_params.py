import json
import tomllib
from types import SimpleNamespace

import pytest

from apps.cmdb.node_configs.config_factory import NodeParamsFactory


@pytest.mark.unit
def test_ssl_cer_node_params_send_domain_and_inst_name_without_secrets():
    task = SimpleNamespace(
        id=88,
        model_id="ssl_cer",
        driver_type="protocol",
        decrypt_credentials={},
        timeout=30,
        params={},
        instances=[
            {"inst_name": "rex-test", "domain": "www.baidu.cn"},
            {"inst_name": "blank", "domain": ""},
        ],
        ip_range="10.0.0.1-10.0.0.2",
        access_point=[{"id": "node-1", "ip": "192.0.2.10"}],
        cycle_value_type="cycle",
        cycle_value="30",
    )
    node_params = NodeParamsFactory.get_node_params(task)
    (config,) = node_params.main()
    headers = tomllib.loads(config["content"])["inputs"]["prometheus"][0]["http_headers"]
    assert headers["cmdbplugin_name"] == "ssl_cer_info"
    assert headers["cmdbexecutor_type"] == "protocol"
    assert headers["cmdbport"] == "443"
    assert "www.baidu.cn" in headers["cmdbhosts"]
    targets = json.loads(headers["cmdbssl_cer_targets"])
    assert {"inst_name": "rex-test", "domain": "www.baidu.cn"} in targets
    assert {"inst_name": "blank", "domain": ""} in targets
    assert "password" not in "".join(headers.keys())
