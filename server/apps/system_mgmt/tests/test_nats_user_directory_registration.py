import nats_client

from apps.system_mgmt import nats_api


LEGACY_REMOTE_USER_DIRECTORY_ENTRYPOINTS = {
    "get_group_users",
    "get_group_users_scoped",
    "get_all_users",
    "search_users",
}


def test_user_directory_entrypoints_keep_temporary_remote_compatibility():
    """仓外消费者迁移完成前保留注册；限时风险接受与退出条件见 #4533。"""
    exported_entrypoints = {
        name for name in LEGACY_REMOTE_USER_DIRECTORY_ENTRYPOINTS if callable(getattr(nats_api, name, None))
    }
    registered_entrypoints = {
        item["name"] for item in nats_client.registry.default_registry.registry.values()
    }

    assert exported_entrypoints == LEGACY_REMOTE_USER_DIRECTORY_ENTRYPOINTS
    assert LEGACY_REMOTE_USER_DIRECTORY_ENTRYPOINTS <= registered_entrypoints
