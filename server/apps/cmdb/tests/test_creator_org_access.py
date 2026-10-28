"""创建者快捷授权必须核对当前用户所属组织，不能只信 Cookie 里的 current_team。"""

import json
from types import SimpleNamespace

from rest_framework import status

from apps.cmdb.views.mixins import CmdbPermissionMixin

ORG_A = 1
ORG_CHILD = 2
ORG_B = 9
DENY_MESSAGE = "抱歉！您没有此实例的权限"


def _request(
    group_list,
    *,
    username="alice",
    current_team="1",
    include_children="0",
    group_tree=None,
    api_current_team=None,
):
    user = SimpleNamespace(
        username=username,
        group_list=group_list,
        group_tree=group_tree or [],
    )
    request = SimpleNamespace(
        user=user,
        COOKIES={
            "current_team": current_team,
            "include_children": include_children,
        },
    )
    if api_current_team is not None:
        request._api_current_team = api_current_team
    return request


def _instance(organization, creator="alice"):
    return {"organization": organization, "_creator": creator, "model_id": "host"}


def _deny_message(response):
    return json.loads(response.content)["message"]


def test_moved_asset_cookie_team_does_not_grant_creator_shortcut():
    """用户只属于组织 A，实例已在 B，Cookie 改成 B 且关闭子组织时不得提前放行。"""
    request = _request([{"id": ORG_A}], current_team=str(ORG_B), include_children="0")
    instance = _instance([ORG_B])

    assert CmdbPermissionMixin.is_creator_with_org_access(request, instance) is False

    response = CmdbPermissionMixin().require_instance_permission(request, instance)
    assert response is not None
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert _deny_message(response) == DENY_MESSAGE


def test_creator_in_authorized_org_still_passes():
    request = _request([{"id": ORG_A}], current_team=str(ORG_A), include_children="0")
    instance = _instance([ORG_A])

    assert CmdbPermissionMixin.is_creator_with_org_access(request, instance) is True
    assert CmdbPermissionMixin().require_instance_permission(request, instance) is None


def test_non_creator_is_denied_even_when_org_matches(monkeypatch):
    monkeypatch.setattr(
        CmdbPermissionMixin,
        "check_instance_permission",
        lambda self, request, instance, operator=None: False,
    )
    request = _request(
        [{"id": ORG_A}],
        username="bob",
        current_team=str(ORG_A),
        include_children="0",
    )
    instance = _instance([ORG_A], creator="alice")

    assert CmdbPermissionMixin.is_creator_with_org_access(request, instance) is False
    response = CmdbPermissionMixin().require_instance_permission(request, instance)
    assert response is not None
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert _deny_message(response) == DENY_MESSAGE


def test_include_children_allows_creator_on_child_of_authorized_parent():
    group_tree = [{"id": ORG_A, "subGroups": [{"id": ORG_CHILD}]}]
    request = _request(
        [{"id": ORG_A}],
        current_team=str(ORG_A),
        include_children="1",
        group_tree=group_tree,
    )
    instance = _instance([ORG_CHILD])

    assert CmdbPermissionMixin.is_creator_with_org_access(request, instance) is True
    assert CmdbPermissionMixin().require_instance_permission(request, instance) is None


def test_include_children_rejects_cookie_switched_to_unauthorized_org():
    # 组织树里即使能走到 B，B 不在 group_list 时也必须拒绝。
    group_tree = [
        {"id": ORG_A, "subGroups": [{"id": ORG_CHILD}]},
        {"id": ORG_B},
    ]
    request = _request(
        [{"id": ORG_A}],
        current_team=str(ORG_B),
        include_children="1",
        group_tree=group_tree,
    )
    instance = _instance([ORG_B])

    assert CmdbPermissionMixin.is_creator_with_org_access(request, instance) is False
    response = CmdbPermissionMixin().require_instance_permission(request, instance)
    assert response is not None
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert _deny_message(response) == DENY_MESSAGE


def test_api_current_team_overrides_cookie_when_authorized():
    request = _request(
        [{"id": ORG_A}],
        current_team=str(ORG_B),
        include_children="0",
        api_current_team=ORG_A,
    )
    instance = _instance([ORG_A])

    assert CmdbPermissionMixin.is_creator_with_org_access(request, instance) is True
    assert CmdbPermissionMixin().require_instance_permission(request, instance) is None
