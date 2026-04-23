from types import SimpleNamespace

from apps.node_mgmt.services import sidecar_cache


def test_node_assignment_add_invalidates_affected_node_etags(monkeypatch):
    deleted_keys = []
    monkeypatch.setattr(sidecar_cache, "cache", SimpleNamespace(delete_many=lambda keys: deleted_keys.extend(keys)))

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

    sidecar_cache.invalidate_assignment_node_etags(
        action="pre_clear",
        reverse=False,
        instance=SimpleNamespace(pk="config-a", nodes=manager),
        pk_set=None,
    )

    assert sorted(deleted_keys) == ["node_etag_node-a", "node_etag_node-b"]


def test_child_and_parent_config_changes_invalidate_render_etag(monkeypatch):
    deleted_keys = []
    monkeypatch.setattr(sidecar_cache, "cache", SimpleNamespace(delete=lambda key: deleted_keys.append(key)))

    sidecar_cache.invalidate_child_config_etag(SimpleNamespace(collector_config_id="config-a"))
    sidecar_cache.invalidate_collector_configuration_etag(SimpleNamespace(pk="config-b"))

    assert deleted_keys == ["configuration_etag_config-a", "configuration_etag_config-b"]


def test_action_changes_invalidate_node_poll_etag(monkeypatch):
    deleted_keys = []
    monkeypatch.setattr(sidecar_cache, "cache", SimpleNamespace(delete_many=lambda keys: deleted_keys.extend(keys)))

    sidecar_cache.invalidate_action_node_etag(SimpleNamespace(node_id="node-a"))

    assert deleted_keys == ["node_etag_node-a"]


def test_deleted_configuration_invalidates_bound_node_poll_etags(monkeypatch):
    deleted_keys = []
    manager = SimpleNamespace(values_list=lambda *args, **kwargs: ["node-a", "node-b"])
    monkeypatch.setattr(sidecar_cache, "cache", SimpleNamespace(delete_many=lambda keys: deleted_keys.extend(keys)))

    sidecar_cache.invalidate_collector_configuration_node_etags(SimpleNamespace(nodes=manager))

    assert sorted(deleted_keys) == ["node_etag_node-a", "node_etag_node-b"]
