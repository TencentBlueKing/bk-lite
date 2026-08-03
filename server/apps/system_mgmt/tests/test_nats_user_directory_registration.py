import nats_client

from apps.system_mgmt import nats_api


LOCAL_ONLY_USER_DIRECTORY_ENTRYPOINTS = {
    "get_group_users",
    "get_group_users_scoped",
    "get_all_users",
    "search_users",
}


def test_user_directory_entrypoints_are_local_only():
    exported_entrypoints = {
        name for name in LOCAL_ONLY_USER_DIRECTORY_ENTRYPOINTS if callable(getattr(nats_api, name, None))
    }
    registered_entrypoints = {
        item["name"] for item in nats_client.registry.default_registry.registry.values()
    }

    assert exported_entrypoints == LOCAL_ONLY_USER_DIRECTORY_ENTRYPOINTS
    assert LOCAL_ONLY_USER_DIRECTORY_ENTRYPOINTS.isdisjoint(registered_entrypoints)
