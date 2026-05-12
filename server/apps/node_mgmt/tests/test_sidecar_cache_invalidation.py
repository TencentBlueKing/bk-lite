from types import SimpleNamespace

import pytest

from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.node_mgmt.models import CloudRegion, SidecarEnv
from apps.node_mgmt.services import cloudregion as cloudregion_service
from apps.node_mgmt.services.cloudregion import RegionService
from apps.node_mgmt.services import sidecar_cache


class _FakeCache:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, timeout=None):
        self.data[key] = value

    def delete_many(self, keys):
        for key in keys:
            self.data.pop(key, None)


def test_node_assignment_add_invalidates_affected_node_etags(monkeypatch):
    deleted_keys = []
    monkeypatch.setattr(sidecar_cache, "cache", SimpleNamespace(delete_many=lambda keys: deleted_keys.extend(keys)))
    monkeypatch.setattr(sidecar_cache.transaction, "on_commit", lambda callback: callback())

    sidecar_cache.invalidate_assignment_node_etags(
        action="post_add",
        reverse=False,
        instance=SimpleNamespace(pk="config-a"),
        pk_set={"node-a", "node-b"},
    )

    assert sorted(deleted_keys) == ["node_etag_node-a", "node_etag_node-b"]


def test_node_assignment_reverse_change_invalidates_node_etag(monkeypatch):
    deleted_keys = []
    monkeypatch.setattr(sidecar_cache, "cache", SimpleNamespace(delete_many=lambda keys: deleted_keys.extend(keys)))
    monkeypatch.setattr(sidecar_cache.transaction, "on_commit", lambda callback: callback())

    sidecar_cache.invalidate_assignment_node_etags(
        action="post_remove",
        reverse=True,
        instance=SimpleNamespace(pk="node-a"),
        pk_set={"config-a"},
    )

    assert deleted_keys == ["node_etag_node-a"]


def test_node_assignment_clear_invalidates_previously_bound_nodes(monkeypatch):
    deleted_keys = []
    manager = SimpleNamespace(values_list=lambda *args, **kwargs: ["node-a", "node-b"])
    monkeypatch.setattr(sidecar_cache, "cache", SimpleNamespace(delete_many=lambda keys: deleted_keys.extend(keys)))
    monkeypatch.setattr(sidecar_cache.transaction, "on_commit", lambda callback: callback())

    sidecar_cache.invalidate_assignment_node_etags(
        action="pre_clear",
        reverse=False,
        instance=SimpleNamespace(pk="config-a", nodes=manager),
        pk_set=None,
    )

    assert sorted(deleted_keys) == ["node_etag_node-a", "node_etag_node-b"]


def test_node_assignment_add_invalidates_node_scoped_configuration_etags(monkeypatch):
    deleted_keys = []
    monkeypatch.setattr(sidecar_cache, "cache", SimpleNamespace(delete_many=lambda keys: deleted_keys.extend(keys)))
    monkeypatch.setattr(sidecar_cache.transaction, "on_commit", lambda callback: callback())

    sidecar_cache.invalidate_assignment_configuration_etags(
        action="post_add",
        reverse=False,
        instance=SimpleNamespace(pk="config-a"),
        pk_set={"node-a", "node-b"},
    )

    assert sorted(deleted_keys) == [
        "configuration_etag_node-a_config-a",
        "configuration_etag_node-b_config-a",
    ]


def test_node_assignment_reverse_change_invalidates_node_scoped_configuration_etags(monkeypatch):
    deleted_keys = []
    monkeypatch.setattr(sidecar_cache, "cache", SimpleNamespace(delete_many=lambda keys: deleted_keys.extend(keys)))
    monkeypatch.setattr(sidecar_cache.transaction, "on_commit", lambda callback: callback())

    sidecar_cache.invalidate_assignment_configuration_etags(
        action="post_remove",
        reverse=True,
        instance=SimpleNamespace(pk="node-a"),
        pk_set={"config-a", "config-b"},
    )

    assert sorted(deleted_keys) == [
        "configuration_etag_node-a_config-a",
        "configuration_etag_node-a_config-b",
    ]


def test_node_assignment_clear_invalidates_previously_bound_configuration_etags(monkeypatch):
    deleted_keys = []
    manager = SimpleNamespace(values_list=lambda *args, **kwargs: ["node-a", "node-b"])
    monkeypatch.setattr(sidecar_cache, "cache", SimpleNamespace(delete_many=lambda keys: deleted_keys.extend(keys)))
    monkeypatch.setattr(sidecar_cache.transaction, "on_commit", lambda callback: callback())

    sidecar_cache.invalidate_assignment_configuration_etags(
        action="pre_clear",
        reverse=False,
        instance=SimpleNamespace(pk="config-a", nodes=manager),
        pk_set=None,
    )

    assert sorted(deleted_keys) == [
        "configuration_etag_node-a_config-a",
        "configuration_etag_node-b_config-a",
    ]


def test_child_and_parent_config_changes_invalidate_render_etag(monkeypatch):
    deleted_keys = []
    monkeypatch.setattr(
        sidecar_cache,
        "_configuration_node_map",
        lambda configuration_ids: {
            configuration_id: {
                "config-a": ["node-a"],
                "config-b": ["node-b"],
                "config-c": ["node-c"],
            }[configuration_id]
            for configuration_id in configuration_ids
        },
    )
    monkeypatch.setattr(
        sidecar_cache,
        "cache",
        SimpleNamespace(
            delete_many=lambda keys: deleted_keys.extend(keys),
        ),
    )
    monkeypatch.setattr(sidecar_cache.transaction, "on_commit", lambda callback: callback())

    sidecar_cache.invalidate_child_config_etag(SimpleNamespace(collector_config_id="config-a"))
    sidecar_cache.invalidate_configuration_etags(["config-b", "config-c"])

    assert deleted_keys == [
        "configuration_etag_node-a_config-a",
        "configuration_etag_node-b_config-b",
        "configuration_etag_node-c_config-c",
    ]


def test_action_changes_invalidate_node_poll_etag(monkeypatch):
    deleted_keys = []
    monkeypatch.setattr(sidecar_cache, "cache", SimpleNamespace(delete_many=lambda keys: deleted_keys.extend(keys)))
    monkeypatch.setattr(sidecar_cache.transaction, "on_commit", lambda callback: callback())

    sidecar_cache.invalidate_action_node_etag(SimpleNamespace(node_id="node-a"))

    assert deleted_keys == ["node_etag_node-a"]


def test_deleted_configuration_invalidates_bound_node_poll_etags(monkeypatch):
    deleted_keys = []
    manager = SimpleNamespace(values_list=lambda *args, **kwargs: ["node-a", "node-b"])
    monkeypatch.setattr(sidecar_cache, "cache", SimpleNamespace(delete_many=lambda keys: deleted_keys.extend(keys)))
    monkeypatch.setattr(sidecar_cache.transaction, "on_commit", lambda callback: callback())

    sidecar_cache.invalidate_collector_configuration_node_etags(SimpleNamespace(nodes=manager))

    assert sorted(deleted_keys) == ["node_etag_node-a", "node_etag_node-b"]


def test_updated_configuration_invalidates_render_and_bound_node_etags(monkeypatch):
    deleted_keys = []
    manager = SimpleNamespace(values_list=lambda *args, **kwargs: ["node-a", "node-b"])
    monkeypatch.setattr(
        sidecar_cache,
        "cache",
        SimpleNamespace(
            delete_many=lambda keys: deleted_keys.extend(keys),
        ),
    )
    monkeypatch.setattr(sidecar_cache.transaction, "on_commit", lambda callback: callback())

    sidecar_cache.invalidate_collector_configuration_related_etags(SimpleNamespace(pk="config-a", nodes=manager))

    assert deleted_keys == [
        "configuration_etag_node-a_config-a",
        "configuration_etag_node-b_config-a",
        "node_etag_node-a",
        "node_etag_node-b",
    ]


def test_configuration_etag_ignores_unbound_nodes(monkeypatch):
    deleted_keys = []
    monkeypatch.setattr(sidecar_cache, "cache", SimpleNamespace(delete_many=lambda keys: deleted_keys.extend(keys)))
    monkeypatch.setattr(sidecar_cache.transaction, "on_commit", lambda callback: callback())

    sidecar_cache.invalidate_configuration_etag("config-a", node_ids=["node-a", None, "node-a"])

    assert deleted_keys == ["configuration_etag_node-a_config-a"]


def test_bulk_create_configs_invalidates_node_etags(monkeypatch):
    invalidated_node_ids = []
    monkeypatch.setattr(sidecar_cache, "invalidate_node_etags", lambda node_ids: invalidated_node_ids.extend(node_ids))
    sidecar_cache.invalidate_bulk_config_node_etags(
        [
            {"id": "config-a", "name": "cfg-a", "content": "a", "node_id": "node-a", "collector_name": "telegraf"},
            {"id": "config-b", "name": "cfg-b", "content": "b", "node_id": "node-b", "collector_name": "telegraf"},
            {"id": "config-c", "name": "cfg-c", "content": "c", "node_id": "node-a", "collector_name": "telegraf"},
        ]
    )

    assert invalidated_node_ids == ["node-a", "node-b", "node-a"]


def test_bulk_create_child_configs_invalidates_configuration_etags(monkeypatch):
    invalidated_configuration_ids = []
    monkeypatch.setattr(
        sidecar_cache,
        "invalidate_configuration_etags",
        lambda configuration_ids: invalidated_configuration_ids.extend(sorted(configuration_ids)),
    )

    sidecar_cache.invalidate_bulk_child_config_etags(
        [
            {"collector_config_id": "config-a"},
            {"collector_config_id": "config-b"},
            {"collector_config_id": "config-a"},
        ]
    )

    assert invalidated_configuration_ids == ["config-a", "config-b"]


@pytest.mark.django_db
def test_cloud_region_env_cache_invalidates_on_save(monkeypatch):
    fake_cache = _FakeCache()
    monkeypatch.setattr(sidecar_cache, "cache", fake_cache)
    monkeypatch.setattr(cloudregion_service, "cache", fake_cache)
    monkeypatch.setattr(sidecar_cache.transaction, "on_commit", lambda callback: callback())

    cloud_region = CloudRegion.objects.create(
        name="cache-sidecar-env-save",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    aes = AESCryptor()
    env = SidecarEnv.objects.create(
        key="NATS_PASSWORD",
        value=aes.encode("secret-v1"),
        type="secret",
        cloud_region=cloud_region,
    )
    cache_key = sidecar_cache.build_sidecar_env_cache_key(cloud_region.id)

    assert RegionService.get_cloud_region_envconfig(cloud_region.id)["NATS_PASSWORD"] == "secret-v1"
    cached_rows = fake_cache.get(cache_key)
    assert cached_rows[0]["value"] == env.value

    env.value = aes.encode("secret-v2")
    env.save(update_fields=["value"])

    assert fake_cache.get(cache_key) is None
    assert RegionService.get_cloud_region_envconfig(cloud_region.id)["NATS_PASSWORD"] == "secret-v2"


@pytest.mark.django_db
def test_cloud_region_env_cache_invalidates_on_delete(monkeypatch):
    fake_cache = _FakeCache()
    monkeypatch.setattr(sidecar_cache, "cache", fake_cache)
    monkeypatch.setattr(cloudregion_service, "cache", fake_cache)
    monkeypatch.setattr(sidecar_cache.transaction, "on_commit", lambda callback: callback())

    cloud_region = CloudRegion.objects.create(
        name="cache-sidecar-env-delete",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )
    aes = AESCryptor()
    env = SidecarEnv.objects.create(
        key="NATS_PASSWORD",
        value=aes.encode("secret-v1"),
        type="secret",
        cloud_region=cloud_region,
    )
    cache_key = sidecar_cache.build_sidecar_env_cache_key(cloud_region.id)

    assert RegionService.get_cloud_region_envconfig(cloud_region.id)["NATS_PASSWORD"] == "secret-v1"

    env.delete()

    assert RegionService.get_cloud_region_envconfig(cloud_region.id) == {}
    assert fake_cache.get(cache_key) == []


def test_cloud_region_envconfig_falls_back_when_secret_decode_fails(monkeypatch):
    bad_secret = "not-valid-ciphertext"

    variables = RegionService._decode_env_rows(
        [
            {"key": "NATS_PASSWORD", "value": bad_secret, "type": "secret"},
            {"key": "NODE_SERVER_URL", "value": "http://bk-lite.example.com", "type": "text"},
        ]
    )

    assert variables == {
        "NATS_PASSWORD": bad_secret,
        "NODE_SERVER_URL": "http://bk-lite.example.com",
    }
