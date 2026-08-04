from types import SimpleNamespace

from apps.cmdb.constants.constants import CollectDriverTypes
from apps.cmdb.node_configs.config_factory import NodeParamsFactory


def _task(credential):
    return SimpleNamespace(
        id=42,
        model_id="influxdb",
        driver_type=CollectDriverTypes.PROTOCOL,
        decrypt_credentials=credential,
        timeout=30,
        params={},
        instances=[
            {
                "_id": "influx-1",
                "model_id": "influxdb",
                "inst_name": "influx.local",
                "ip_addr": "10.0.0.8",
            }
        ],
        ip_range="",
        access_point=[{"id": "node-1"}],
        cycle_value_type="cycle",
        cycle_value=5,
    )


def test_influxdb_node_params_without_token():
    params_cls = NodeParamsFactory.get_params_class(
        "influxdb", CollectDriverTypes.PROTOCOL
    )
    node_params = params_cls(
        _task(
            {
                "port": 8086,
                "scheme": "http",
                "verify_tls": True,
            }
        )
    )

    assert node_params.set_credential() == {
        "port": 8086,
        "ssl": False,
        "verify_tls": True,
    }
    assert node_params.env_config() == {}
    assert node_params.get_hosts() == ("host", "10.0.0.8")


def test_influxdb_node_params_uses_environment_reference_for_token():
    params_cls = NodeParamsFactory.get_params_class(
        "influxdb", CollectDriverTypes.PROTOCOL
    )
    node_params = params_cls(
        _task(
            {
                "port": 8443,
                "scheme": "https",
                "verify_tls": False,
                "token": "operator-secret",
            }
        )
    )

    assert node_params.set_credential() == {
        "port": 8443,
        "ssl": True,
        "verify_tls": False,
        "token": "${PASSWORD_token_cmdb_42}",
    }
    assert node_params.env_config() == {
        "PASSWORD_token_cmdb_42": "operator-secret"
    }
