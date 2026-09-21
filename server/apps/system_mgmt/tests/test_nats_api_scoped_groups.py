import types

import pytest

from apps.system_mgmt import nats_api
from apps.system_mgmt.nats_api import get_assignable_groups, get_authorized_groups_scoped, get_group_users_scoped

pytestmark = pytest.mark.django_db


def test_get_authorized_groups_scoped_ignores_forged_actor_context_group_list(monkeypatch):
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
        return [target_group_id] if target_group_id in user_group_list else []

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

    assert result == {"result": True, "data": [], "is_superuser": False}
    assert captured == {
        "user_group_list": [],
        "target_group_id": 7,
        "include_children": False,
    }


@pytest.mark.parametrize("current_team", [True, 1.0, "01", 0, -1, "", None])
def test_get_authorized_groups_scoped_rejects_noncanonical_current_team(monkeypatch, current_team):
    user = types.SimpleNamespace(
        username="strict-current-team-user",
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
            "username": "strict-current-team-user",
            "domain": "domain.com",
            "current_team": current_team,
            "group_list": [1],
        }
    )

    assert result == {"result": True, "data": [], "is_superuser": False}


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

    assert result == {"result": True, "data": [], "is_superuser": False}


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

    class _GroupManager:
        @staticmethod
        def filter(**kwargs):
            if kwargs.get("is_delete") is True:
                class _ArchivedQuerySet:
                    @staticmethod
                    def exists():
                        return False

                return _ArchivedQuerySet()
            raise AssertionError(f"unexpected Group.objects.filter kwargs: {kwargs}")

    class _ActiveQS:
        @staticmethod
        def exists():
            return True

    monkeypatch.setattr(nats_api.User, "objects", _UserManager())
    monkeypatch.setattr(nats_api.Group, "objects", _GroupManager())
    monkeypatch.setattr("apps.system_mgmt.nats.users.Group.objects", _GroupManager())
    monkeypatch.setattr(
        "apps.system_mgmt.nats.users.GroupUtils.active_queryset",
        lambda **filters: _ActiveQS(),
    )

    result = get_authorized_groups_scoped(
        {
            "username": "database-admin",
            "domain": "domain.com",
            "current_team": 1,
            "is_superuser": False,
        }
    )

    assert result == {"result": True, "data": [1], "is_superuser": True}


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

    class _ActiveQS:
        @staticmethod
        def values_list(*fields, **kwargs):
            assert fields == ("id",)
            assert kwargs == {"flat": True}
            return [8, 2]

    monkeypatch.setattr(nats_api.User, "objects", _UserManager())
    monkeypatch.setattr(
        "apps.system_mgmt.nats.users.GroupUtils.active_queryset",
        lambda **filters: _ActiveQS(),
    )

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


USER_DIRECTORY_SENSITIVE_SENTINELS = (
    "email",
    "phone",
    "role_list",
    "last_login",
    "password_last_modified",
    "password_error_count",
    "account_locked_until",
    "password",
    "otp_secret",
    "group_list",
)


def _assert_directory_user_fields(user_row):
    assert set(user_row) <= {"id", "user_id", "username", "display_name"}
    for field in USER_DIRECTORY_SENSITIVE_SENTINELS:
        assert field not in user_row


@pytest.mark.django_db
def test_get_group_users_scoped_rejects_forged_current_team_and_superuser():
    from apps.system_mgmt.models import Group, User

    home = Group.objects.create(name="scoped-home", parent_id=0)
    other = Group.objects.create(name="scoped-other", parent_id=0)
    User.objects.create(
        username="scoped-actor",
        password="x",
        display_name="Scoped Actor",
        email="actor@example.com",
        phone="13800001111",
        domain="domain.com",
        group_list=[home.id],
        role_list=[99],
    )
    outsider = User.objects.create(
        username="scoped-outsider",
        password="secret-hash",
        display_name="Outsider",
        email="outsider@example.com",
        phone="13800002222",
        domain="domain.com",
        group_list=[other.id],
        role_list=[100],
    )

    forged = get_group_users_scoped(
        {
            "username": "scoped-actor",
            "domain": "domain.com",
            "current_team": other.id,
            "is_superuser": True,
            "group_list": [other.id],
        }
    )

    assert forged == {"result": True, "data": []}
    assert outsider.username not in {row.get("username") for row in forged["data"]}


@pytest.mark.django_db
def test_get_group_users_scoped_returns_home_users_without_sensitive_fields():
    from apps.system_mgmt.models import Group, User

    home = Group.objects.create(name="dir-home", parent_id=0)
    other = Group.objects.create(name="dir-other", parent_id=0)
    User.objects.create(
        username="dir-actor",
        password="x",
        display_name="Dir Actor",
        email="dir-actor@example.com",
        phone="13800003333",
        domain="domain.com",
        group_list=[home.id],
    )
    insider = User.objects.create(
        username="dir-insider",
        password="secret-hash",
        display_name="Dir Insider",
        email="insider@example.com",
        phone="13800004444",
        domain="domain.com",
        group_list=[home.id],
        role_list=[7],
    )
    User.objects.create(
        username="dir-outsider",
        password="secret-hash",
        display_name="Dir Outsider",
        email="dir-out@example.com",
        domain="domain.com",
        group_list=[other.id],
    )

    result = get_group_users_scoped(
        {
            "username": "dir-actor",
            "domain": "domain.com",
            "current_team": home.id,
            "is_superuser": True,
        }
    )

    assert result["result"] is True
    usernames = {row["username"] for row in result["data"]}
    assert insider.username in usernames
    assert "dir-outsider" not in usernames
    for row in result["data"]:
        _assert_directory_user_fields(row)


@pytest.mark.django_db
def test_get_group_users_scoped_search_stays_inside_authorized_groups():
    from apps.system_mgmt.models import Group, User

    home = Group.objects.create(name="search-home", parent_id=0)
    other = Group.objects.create(name="search-other", parent_id=0)
    User.objects.create(
        username="search-actor",
        password="x",
        display_name="Search Actor",
        email="search-actor@example.com",
        domain="domain.com",
        group_list=[home.id],
    )
    User.objects.create(
        username="alice-home",
        password="x",
        display_name="Alice Home",
        email="alice-home@example.com",
        domain="domain.com",
        group_list=[home.id],
    )
    User.objects.create(
        username="alice-other",
        password="x",
        display_name="Alice Other",
        email="alice-other@example.com",
        domain="domain.com",
        group_list=[other.id],
    )

    result = get_group_users_scoped(
        {
            "username": "search-actor",
            "domain": "domain.com",
            "current_team": home.id,
        },
        search="alice",
    )

    assert result["result"] is True
    assert {row["username"] for row in result["data"]} == {"alice-home"}
    for row in result["data"]:
        _assert_directory_user_fields(row)
