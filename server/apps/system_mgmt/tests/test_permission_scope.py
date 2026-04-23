from types import SimpleNamespace

from apps.system_mgmt import nats_api


class _QuerySetStub:
    def __init__(self, values=None, first_value=None):
        self._values = values or []
        self._first_value = first_value

    def filter(self, *args, **kwargs):
        return self

    def values_list(self, *args, **kwargs):
        return self._values

    def first(self):
        return self._first_value


class _UserManagerStub:
    def __init__(self, user):
        self._user = user

    def filter(self, *args, **kwargs):
        return _QuerySetStub(first_value=self._user)


class _RoleManagerStub:
    def filter(self, *args, **kwargs):
        return _QuerySetStub(values=[])


class _GroupManagerStub:
    def filter(self, *args, **kwargs):
        return _QuerySetStub(first_value=None)


def _patch_permission_models(monkeypatch, group_list):
    user = SimpleNamespace(username="node_viewer", domain="domain.com", group_list=group_list)
    monkeypatch.setattr(nats_api.User, "objects", _UserManagerStub(user))
    monkeypatch.setattr(nats_api.Role, "objects", _RoleManagerStub())
    monkeypatch.setattr(nats_api.Group, "objects", _GroupManagerStub())
    monkeypatch.setattr(nats_api, "get_user_all_roles", lambda user_obj: [])
    return user


def test_prepare_user_rules_query_rejects_forged_current_team(monkeypatch):
    user = _patch_permission_models(monkeypatch, group_list=[1])

    result = nats_api._prepare_user_rules_query(2, "node_viewer", "domain.com", "node", False)

    assert result == (user, [], [], False, False)


def test_prepare_user_rules_query_keeps_valid_current_team_scope(monkeypatch):
    user = _patch_permission_models(monkeypatch, group_list=[1])

    result = nats_api._prepare_user_rules_query(1, "node_viewer", "domain.com", "node", False)

    assert result == (user, [1], [1], False, False)
