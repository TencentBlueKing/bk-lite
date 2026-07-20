from types import SimpleNamespace

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.current_team_scope import (
    CurrentTeamDataScope,
    resolve_assignable_organization_ids,
    resolve_current_team_data_scope,
    scope_permission_queryset,
    validate_assignable_organizations,
)


pytestmark = pytest.mark.unit


def make_request(*, is_superuser=False, current_team=1, include_children=False):
    return SimpleNamespace(
        COOKIES={
            **({"current_team": str(current_team)} if current_team is not None else {}),
            **({"include_children": "1"} if include_children else {}),
        },
        user=SimpleNamespace(
            username="admin",
            domain="domain.com",
            group_list=[1, 2],
            is_superuser=is_superuser,
        ),
    )


def patch_scoped_groups(monkeypatch, groups):
    class _SystemMgmt:
        def get_authorized_groups_scoped(self, actor_context, include_children=False):
            return {"result": True, "data": groups}

        def get_assignable_groups(self, actor_context):
            return {"result": True, "data": groups}

    monkeypatch.setattr("apps.core.utils.current_team_scope.SystemMgmt", _SystemMgmt)


def test_superuser_scope_is_current_team_only(monkeypatch):
    request = make_request(is_superuser=True, current_team=1)
    patch_scoped_groups(monkeypatch, [1])

    assert resolve_current_team_data_scope(request).data_team_ids == frozenset({1})


@pytest.mark.django_db
def test_instance_permission_cannot_cross_current_team(monkeypatch):
    from apps.system_mgmt.models import Group

    own = Group.objects.create(name="current-team-own", parent_id=0)
    foreign = Group.objects.create(name="current-team-foreign", parent_id=0)
    permission = {"team": [], "instance": [{"id": foreign.id, "permission": ["View"]}]}

    qs = scope_permission_queryset(
        Group,
        permission,
        CurrentTeamDataScope(
            current_team=own.id,
            data_team_ids=frozenset({own.id}),
            include_children=False,
            username="admin",
            domain="domain.com",
            is_superuser=True,
        ),
        team_key="id__in",
    )

    assert list(qs.values_list("id", flat=True)) == []
    assert own.id != foreign.id


def test_missing_current_team_fails_closed():
    with pytest.raises(BaseAppException, match="current_team"):
        resolve_current_team_data_scope(make_request(current_team=None))


def test_assignable_organizations_are_resolved_from_server_context(monkeypatch):
    request = make_request(current_team=1)
    patch_scoped_groups(monkeypatch, [1, 2, 3])

    assert resolve_assignable_organization_ids(request) == frozenset({1, 2, 3})


def test_validate_assignable_organizations_rejects_unassigned_request_id(monkeypatch):
    request = make_request(current_team=1)
    patch_scoped_groups(monkeypatch, [1, 2])

    with pytest.raises(BaseAppException, match="organization"):
        validate_assignable_organizations(request, [1, 3])
