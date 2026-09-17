from types import SimpleNamespace
from unittest.mock import Mock
import json

import pytest

from apps.core.exceptions.base_app_exception import ForbiddenException
from apps.core.utils.current_team_scope import CurrentTeamDataScope
from apps.log.models import CollectInstance, CollectInstanceOrganization, CollectType
from apps.log.views.collect_config import CollectInstanceViewSet

pytestmark = pytest.mark.django_db


def _user(*, is_superuser=False):
    return SimpleNamespace(
        username="alice",
        domain="domain.com",
        is_superuser=is_superuser,
        locale="zh-Hans",
        group_list=[{"id": 1, "name": "Team 1"}],
        is_authenticated=True,
    )


def _request(*, is_superuser=False, unassigned=False, data=None):
    query = {"unassigned": "true"} if unassigned else {}
    return SimpleNamespace(
        user=_user(is_superuser=is_superuser),
        data=data or {"page": 1, "page_size": 20},
        GET=query,
        query_params=query,
        COOKIES={"current_team": "1", "include_children": "0"},
    )


def _scope(*, is_superuser=False):
    return CurrentTeamDataScope(1, frozenset({1}), False, "alice", "domain.com", is_superuser)


def _collect_type():
    return CollectType.objects.create(name="file", collector="Vector", icon="file")


def _patch_scope(monkeypatch, *, is_superuser=False):
    monkeypatch.setattr(
        "apps.log.views.collect_config.LogAccessScopeService.get_data_scope",
        lambda request: _scope(is_superuser=is_superuser),
    )
    monkeypatch.setattr(
        "apps.log.services.collect_type.NodeMgmt",
        lambda: SimpleNamespace(get_node_names_by_ids=lambda ids: []),
    )


def _search_ids(response):
    payload = json.loads(response.content)
    return [item["id"] for item in payload["data"]["items"]]


def test_superuser_default_search_hides_unassigned_instances(monkeypatch):
    collect_type = _collect_type()
    assigned = CollectInstance.objects.create(id="log-assigned", name="assigned", collect_type=collect_type)
    CollectInstanceOrganization.objects.create(collect_instance=assigned, organization=1)
    CollectInstance.objects.create(id="log-ghost", name="ghost", collect_type=collect_type)
    _patch_scope(monkeypatch, is_superuser=True)

    response = CollectInstanceViewSet().search(
        _request(is_superuser=True, data={"page": 1, "page_size": 20, "collect_type_id": collect_type.id})
    )

    assert assigned.id in _search_ids(response)
    assert "log-ghost" not in _search_ids(response)


def test_superuser_unassigned_search_shows_only_zero_org_instances(monkeypatch):
    collect_type = _collect_type()
    assigned = CollectInstance.objects.create(id="log-assigned-u", name="assigned", collect_type=collect_type)
    CollectInstanceOrganization.objects.create(collect_instance=assigned, organization=1)
    ghost = CollectInstance.objects.create(id="log-ghost-u", name="ghost", collect_type=collect_type)
    _patch_scope(monkeypatch, is_superuser=True)

    response = CollectInstanceViewSet().search(
        _request(
            is_superuser=True,
            unassigned=True,
            data={"page": 1, "page_size": 20, "collect_type_id": collect_type.id},
        )
    )

    assert _search_ids(response) == [ghost.id]


def test_non_superuser_unassigned_search_is_forbidden(monkeypatch):
    _patch_scope(monkeypatch, is_superuser=False)

    with pytest.raises(ForbiddenException):
        CollectInstanceViewSet().search(_request(unassigned=True, data={"page": 1, "page_size": 20}))


def test_superuser_can_set_organization_on_unassigned_instance(monkeypatch):
    collect_type = _collect_type()
    ghost = CollectInstance.objects.create(id="log-ghost-set", name="ghost", collect_type=collect_type)
    monkeypatch.setattr(
        "apps.log.views.collect_config.LogAccessScopeService.get_data_scope",
        lambda request: _scope(is_superuser=True),
    )
    monkeypatch.setattr(
        "apps.core.utils.current_team_scope.SystemMgmt.get_assignable_groups",
        Mock(return_value={"result": True, "data": [1, 2]}),
    )

    response = CollectInstanceViewSet().set_organizations(
        _request(is_superuser=True, data={"instance_ids": [ghost.id], "organizations": [1]})
    )

    assert response.status_code == 200
    assert set(CollectInstanceOrganization.objects.filter(collect_instance=ghost).values_list("organization", flat=True)) == {1}


def test_superuser_can_delete_unassigned_instance(monkeypatch):
    collect_type = _collect_type()
    ghost = CollectInstance.objects.create(id="log-ghost-del", name="ghost", collect_type=collect_type)
    monkeypatch.setattr(
        "apps.log.views.collect_config.LogAccessScopeService.get_data_scope",
        lambda request: _scope(is_superuser=True),
    )
    monkeypatch.setattr("apps.log.views.collect_config.NodeMgmt", Mock())

    response = CollectInstanceViewSet().remove_collect_instance(
        _request(is_superuser=True, data={"instance_ids": [ghost.id]})
    )

    assert response.status_code == 200
    assert not CollectInstance.objects.filter(id=ghost.id).exists()
