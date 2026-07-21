import types

import pytest

from apps.system_mgmt import nats_api
from apps.system_mgmt.nats_api import get_assignable_groups, get_authorized_groups_scoped, get_group_users_scoped


def test_get_authorized_groups_scoped_prefers_actor_context_group_list(monkeypatch):
    user = types.SimpleNamespace(
        username="scope-context-user",
        domain="domain.com",
        group_list=[],
        role_list=[],
    )

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


def test_get_authorized_groups_scoped_rejects_forged_superuser_claim(monkeypatch):
    user = types.SimpleNamespace(
        username="ordinary-user",
        domain="domain.com",
        group_list=[1],
        is_superuser=False,
    )

    class _UserQuerySet:
        @staticmethod
        def first():
            return user

    class _UserManager:
        @staticmethod
        def filter(**kwargs):
            return _UserQuerySet()

    monkeypatch.setattr(nats_api.User, "objects", _UserManager())

    result = get_authorized_groups_scoped(
        {
            "username": "ordinary-user",
            "domain": "domain.com",
            "current_team": 2,
            "is_superuser": True,
        }
    )

    assert result == {"result": True, "data": []}


def test_get_authorized_groups_scoped_uses_persisted_superuser_flag(monkeypatch):
    user = types.SimpleNamespace(
        username="database-admin",
        domain="domain.com",
        group_list=[],
        is_superuser=True,
    )

    class _UserQuerySet:
        @staticmethod
        def first():
            return user

    class _UserManager:
        @staticmethod
        def filter(**kwargs):
            return _UserQuerySet()

    monkeypatch.setattr(nats_api.User, "objects", _UserManager())

    result = get_authorized_groups_scoped(
        {
            "username": "database-admin",
            "domain": "domain.com",
            "current_team": 1,
            "is_superuser": False,
        }
    )

    assert result == {"result": True, "data": [1]}


@pytest.mark.django_db
def test_get_group_users_scoped_filters_json_group_list_with_contains(monkeypatch):
    actor = types.SimpleNamespace(
        username="actor",
        domain="domain.com",
        group_list=[7],
        role_list=[],
    )
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


@pytest.mark.django_db
def test_get_assignable_groups_uses_persisted_authorization_not_actor_group_list(monkeypatch):
    user = types.SimpleNamespace(
        username="actor",
        domain="domain.com",
        group_list=[7, 8],
        role_list=[],
    )

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

    def fake_get_group_with_descendants(group_ids):
        captured["group_ids"] = group_ids
        return [7, 8, 9]

    monkeypatch.setattr(nats_api.GroupUtils, "get_group_with_descendants", fake_get_group_with_descendants)

    result = get_assignable_groups(
        {
            "username": "actor",
            "domain": "domain.com",
            "group_list": [999],
            "is_superuser": False,
        }
    )

    assert result == {"result": True, "data": [7, 8, 9]}
    assert captured == {"group_ids": [7, 8]}


def test_get_assignable_groups_returns_all_existing_groups_for_superuser(monkeypatch):
    user = types.SimpleNamespace(username="admin", domain="domain.com", group_list=[], is_superuser=True)

    class _UserQuerySet:
        @staticmethod
        def first():
            return user

    class _UserManager:
        @staticmethod
        def filter(**kwargs):
            return _UserQuerySet()

    class _GroupManager:
        @staticmethod
        def values_list(*fields, **kwargs):
            assert fields == ("id",)
            assert kwargs == {"flat": True}
            return [8, 2]

    monkeypatch.setattr(nats_api.User, "objects", _UserManager())
    monkeypatch.setattr(nats_api.Group, "objects", _GroupManager())

    result = get_assignable_groups({"username": "admin", "domain": "domain.com", "is_superuser": True})

    assert result == {"result": True, "data": [8, 2]}


@pytest.mark.django_db
def test_get_assignable_groups_expands_persisted_root_to_unlisted_descendant():
    from apps.system_mgmt.models import Group, User

    root = Group.objects.create(name="assignable-root", parent_id=0)
    child = Group.objects.create(name="assignable-child", parent_id=root.id)
    User.objects.create(
        username="assignable-actor",
        password="x",
        display_name="assignable actor",
        email="assignable-actor@example.com",
        domain="domain.com",
        group_list=[root.id],
    )

    result = get_assignable_groups({"username": "assignable-actor", "domain": "domain.com"})

    assert set(result["data"]) == {root.id, child.id}
