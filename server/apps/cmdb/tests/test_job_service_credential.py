"""Redis / MongoDB 服务口令离开节点参数时只以占位符出现。"""

from types import SimpleNamespace

from apps.cmdb.node_configs.databases.mongodb import MongoDBParams
from apps.cmdb.node_configs.ssh.redis import RedisNodeParams
from apps.cmdb.services.encrypt_collect_password import get_collect_model_passwords
from apps.cmdb.tests.e2e.test_credential_delivery_pipeline import _resolve_stargazer_params


def _instance(model_id):
    return SimpleNamespace(
        id=42,
        model_id=model_id,
        timeout=60,
        params={},
        access_point=[{"id": "node-1"}],
        instances=[{"ip_addr": "10.10.41.149", "model_id": model_id}],
        ip_range="",
        driver_type="job",
        task_type="db",
        cycle_value_type="cycle",
        cycle_value=5,
    )


def test_redis_and_mongodb_encrypt_the_service_password():
    assert "service_password" in get_collect_model_passwords(collect_model_id="redis")
    assert "service_password" in get_collect_model_passwords(collect_model_id="mongodb")
    assert "password" in get_collect_model_passwords(collect_model_id="redis")


def test_service_password_placeholder_is_separate_from_the_ssh_password():
    cases = [
        (RedisNodeParams, "redis", "redis-secret", None),
        (MongoDBParams, "mongodb", "mongo-secret", "admin"),
    ]
    for node_cls, model_id, secret, auth_source in cases:
        credential = {
            "username": "root",
            "password": "ssh-secret",
            "port": 22,
            "service_username": "reader",
            "service_password": secret,
        }
        if auth_source:
            credential["auth_source"] = auth_source
        node = node_cls(_instance(model_id), resolve_credentials=False, resolved_credentials=credential)
        headers = node.custom_headers()
        env = node.env_config()
        rendered = "\n".join(str(value) for value in headers.values())

        assert secret not in rendered
        assert "ssh-secret" not in rendered
        params = _resolve_stargazer_params(headers, env)
        assert params["password"] == "ssh-secret"
        assert params["service_password"] == secret
        assert params["service_username"] == "reader"
        assert params["username"] == "root"
        if auth_source:
            assert params["auth_source"] == auth_source
