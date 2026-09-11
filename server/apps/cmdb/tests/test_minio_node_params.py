from types import SimpleNamespace

import pytest
import toml

from apps.cmdb.node_configs.config_factory import NodeParamsFactory


@pytest.mark.unit
def test_minio_task_renders_telegraf_config_with_ssh_credentials():
    task = SimpleNamespace(
        id=42,
        model_id="minio",
        driver_type="job",
        decrypt_credentials={"username": "collector", "password": "minio-secret-sentinel", "port": 2222},
        timeout=60,
        params={},
        instances=[{"ip_addr": "192.0.2.42"}],
        ip_range="",
        access_point=[{"id": "node-1"}],
        cycle_value_type="cycle",
        cycle_value="30",
    )

    node_params = NodeParamsFactory.get_node_params(task)
    (config,) = node_params.main()
    (source,) = toml.loads(config["content"])["inputs"]["prometheus"]
    headers = source["http_headers"]

    assert config["id"] == "cmdb_42"
    assert config["collector_name"] == "Telegraf"
    assert config["node_id"] == "node-1"
    assert source["urls"] == ["${STARGAZER_URL}/api/collect/collect_info"]
    assert source["interval"] == "1800s"
    assert headers["cmdbmodel_id"] == "minio"
    assert headers["cmdbplugin_name"] == "minio_info"
    assert headers["cmdbexecutor_type"] == "job"
    assert headers["cmdbhosts"] == "192.0.2.42"
    assert headers["cmdbusername"] == "collector"
    assert headers["cmdbport"] == "2222"
    assert headers["cmdbpassword"] == "${PASSWORD_password_cmdb_42}"
    assert "minio-secret-sentinel" not in config["content"]
    assert config["env_config"] == {"PASSWORD_password_cmdb_42": "minio-secret-sentinel"}
    assert node_params.main(operator="delete") == ["cmdb_42"]
