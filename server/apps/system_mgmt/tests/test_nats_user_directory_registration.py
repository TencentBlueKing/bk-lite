import nats_client

from apps.system_mgmt import nats_api


LOCAL_ONLY_USER_DIRECTORY_ENTRYPOINTS = {
    "get_group_users",
    "get_group_users_scoped",
    "get_all_users",
    "search_users",
}

LOCAL_ONLY_IDENTITY_SCOPED_ENTRYPOINTS = {
    "get_authorized_groups_scoped",
    "search_channel_list_scoped",
}


def test_identity_sensitive_entrypoints_are_local_only():
    local_only_entrypoints = LOCAL_ONLY_USER_DIRECTORY_ENTRYPOINTS | LOCAL_ONLY_IDENTITY_SCOPED_ENTRYPOINTS
    exported_entrypoints = {
        name for name in local_only_entrypoints if callable(getattr(nats_api, name, None))
    }
    registered_entrypoints = {
        item["name"] for item in nats_client.registry.default_registry.registry.values()
    }

    assert exported_entrypoints == local_only_entrypoints
    assert local_only_entrypoints.isdisjoint(registered_entrypoints)
