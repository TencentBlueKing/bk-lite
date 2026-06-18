import types

from apps.system_mgmt import nats_api
from apps.system_mgmt.nats_api import get_authorized_groups_scoped, get_group_users_scoped


def test_get_authorized_groups_scoped_prefers_actor_context_group_list(monkeypatch):
    user = types.SimpleNamespace(username="scope-context-user", domain="domain.com", group_list=[])

    class _UserQuerySet:
        @staticmethod
        def first():
            return user

    class _UserManager:
        @staticmethod
        def filter(**kwargs):
            return _UserQuerySet()

    monkeypatch.setattr(nats_api.User, "objects", _UserManager())

    captured = {}

    def fake_get_user_authorized_child_groups(user_group_list, target_group_id, include_children=False):
        captured["user_group_list"] = user_group_list
        captured["target_group_id"] = target_group_id
        captured["include_children"] = include_children
        return [7]

    monkeypatch.setattr(nats_api.GroupUtils, "get_user_authorized_child_groups", fake_get_user_authorized_child_groups)

    result = get_authorized_groups_scoped(
        {
            "username": "scope-context-user",
            "domain": "domain.com",
            "current_team": 7,
            "is_superuser": False,
            "group_list": [7],
        }
    )

    assert result == {"result": True, "data": [7]}
    assert captured == {
        "user_group_list": [7],
        "target_group_id": 7,
        "include_children": False,
    }


def test_get_group_users_scoped_filters_json_group_list_with_contains(monkeypatch):
    actor = types.SimpleNamespace(username="actor", domain="domain.com", group_list=[7])
    user_rows = [{"id": 3, "username": "test", "display_name": "test"}]

    class _ActorQuerySet:
        @staticmethod
        def first():
            return actor

    class _UserQuerySet:
        @staticmethod
        def values(*fields):
            return user_rows

    class _UserManager:
        def __init__(self):
            self.calls = []

        def filter(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            if kwargs == {"username": "actor", "domain": "domain.com"}:
                return _ActorQuerySet()
            return _UserQuerySet()

    user_manager = _UserManager()
    monkeypatch.setattr(nats_api.User, "objects", user_manager)
    monkeypatch.setattr(
        nats_api.GroupUtils,
        "get_user_authorized_child_groups",
        lambda user_group_list, target_group_id, include_children=False: [7],
    )

    result = get_group_users_scoped(
        {
            "username": "actor",
            "domain": "domain.com",
            "current_team": 7,
            "is_superuser": False,
            "group_list": [7],
        }
    )

    assert result == {"result": True, "data": user_rows}
    args, kwargs = user_manager.calls[1]
    assert kwargs == {}
    assert args[0].children == [("group_list__contains", 7)]
