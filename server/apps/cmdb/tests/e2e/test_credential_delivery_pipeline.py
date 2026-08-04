import re

import pytest

from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.node_configs.config_factory import NodeParamsFactory


ENV_REFERENCE = re.compile(r"^\$\{([^}]+)}$")


def _resolve_stargazer_params(headers, env):
    params = {}
    for key, value in headers.items():
        if not key.startswith("cmdb"):
            continue
        field = key.removeprefix("cmdb")
        match = ENV_REFERENCE.match(str(value))
        params[field] = env[match.group(1)] if match else value
    return params


def _persist_task(*, model_id, task_type, credential, instances):
    task = CollectModels.objects.create(
        name=f"{model_id}-credential-delivery",
        task_type=task_type,
        driver_type=CollectDriverTypes.PROTOCOL,
        model_id=model_id,
        cycle_value_type="cycle",
        cycle_value="5",
        instances=instances,
        access_point=[{"id": "node-1"}],
        credential=credential,
        timeout=60,
        params={},
    )
    task.refresh_from_db()
    return task


@pytest.mark.django_db
def test_influxdb_token_survives_storage_node_management_and_stargazer():
    task = _persist_task(
        model_id="influxdb",
        task_type=CollectPluginTypes.PROTOCOL,
        credential={
            "scheme": "https",
            "port": 8443,
            "verify_tls": False,
            "token": "operator-token",
        },
        instances=[
            {
                "_id": "influx-1",
                "model_id": "influxdb",
                "ip_addr": "10.0.0.8",
            }
        ],
    )

    assert task.credential["token"].startswith("enc:")
    node = NodeParamsFactory.get_node_params(task)
    payload = node.main("push")[0]
    assert "operator-token" not in payload["content"]

    params = _resolve_stargazer_params(
        node.custom_headers(),
        payload["env_config"],
    )
    assert params["host"] == "10.0.0.8"
    assert params["port"] == "8443"
    assert params["ssl"] == "True"
    assert params["verify_tls"] == "False"
    assert params["token"] == "operator-token"


@pytest.mark.django_db
def test_legacy_platform_aksk_survives_delivery_as_collector_username_password():
    task = _persist_task(
        model_id="fusioninsight",
        task_type=CollectPluginTypes.CLOUD,
        credential={
            "accessKey": "legacy-reader",
            "accessSecret": "legacy-secret",
        },
        instances=[
            {
                "_id": "fi-1",
                "model_id": "fusioninsight",
                "endpoint": "https://fi.example.com:9443/web",
            }
        ],
    )

    assert task.credential["accessKey"].startswith("enc:")
    assert task.credential["accessSecret"].startswith("enc:")
    node = NodeParamsFactory.get_node_params(task)
    payload = node.main("push")[0]
    assert "legacy-reader" not in payload["content"]
    assert "legacy-secret" not in payload["content"]

    params = _resolve_stargazer_params(
        node.custom_headers(),
        payload["env_config"],
    )
    assert params["username"] == "legacy-reader"
    assert params["password"] == "legacy-secret"
    assert params["host"] == "fi.example.com"
    assert params["port"] == "9443"


@pytest.mark.django_db
def test_cloud_scope_fields_survive_delivery_without_key_renaming():
    qcloud = _persist_task(
        model_id="qcloud",
        task_type=CollectPluginTypes.CLOUD,
        credential={
            "accessKey": "qcloud-ak",
            "accessSecret": "qcloud-sk",
            "regions": {
                "resource_id": "ap-shanghai",
                "resource_name": "华东地区（上海）",
            },
        },
        instances=[
            {
                "_id": "qcloud-1",
                "model_id": "qcloud",
                "endpoint": "https://cloud.tencent.com",
            }
        ],
    )
    qcloud_node = NodeParamsFactory.get_node_params(qcloud)
    qcloud_payload = qcloud_node.main("push")[0]
    qcloud_params = _resolve_stargazer_params(
        qcloud_node.custom_headers(),
        qcloud_payload["env_config"],
    )
    assert qcloud_params["secret_id"] == "qcloud-ak"
    assert qcloud_params["secret_key"] == "qcloud-sk"
    assert qcloud_params["region_id"] == "ap-shanghai"

    hwcloud = _persist_task(
        model_id="hwcloud",
        task_type=CollectPluginTypes.CLOUD,
        credential={
            "accessKey": "hwcloud-ak",
            "accessSecret": "hwcloud-sk",
            "project_id": "project-123",
            "regions": {
                "resource_id": "cn-north-4",
                "resource_name": "华北-北京四",
            },
        },
        instances=[
            {
                "_id": "hwcloud-1",
                "model_id": "hwcloud",
                "endpoint": "https://iam.myhuaweicloud.com",
            }
        ],
    )
    hwcloud_node = NodeParamsFactory.get_node_params(hwcloud)
    hwcloud_payload = hwcloud_node.main("push")[0]
    hwcloud_params = _resolve_stargazer_params(
        hwcloud_node.custom_headers(),
        hwcloud_payload["env_config"],
    )
    assert hwcloud_params["accessKey"] == "hwcloud-ak"
    assert hwcloud_params["accessSecret"] == "hwcloud-sk"
    assert hwcloud_params["project_id"] == "project-123"
    assert hwcloud_params["region"] == "cn-north-4"
