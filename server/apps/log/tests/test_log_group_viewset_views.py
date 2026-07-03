"""LogGroupViewSet 视图层真实行为测试。

只 mock 权限边界（get_permission_rules），其余走真实 DRF + DB。
断言真实 HTTP 状态、响应体与数据库副作用。
"""
import pytest
from rest_framework import status

from apps.log.models.log_group import LogGroup, LogGroupOrganization


def _mock_permission(mocker, teams=None, instance_permissions=None):
    """直接 patch access_scope 使用的权限规则获取函数。"""
    mocker.patch(
        "apps.log.services.access_scope.get_permission_rules",
        return_value={
            "team": teams or [],
            "instance": instance_permissions or [],
        },
    )


@pytest.mark.django_db
def test_list_returns_only_accessible_groups_with_default_permission(api_client, authenticated_user, mocker):
    LogGroup.objects.create(id="g-1", name="可见组", rule={})
    LogGroupOrganization.objects.create(log_group_id="g-1", organization=1)
    LogGroup.objects.create(id="g-2", name="不可见组", rule={})
    LogGroupOrganization.objects.create(log_group_id="g-2", organization=99)
    _mock_permission(mocker, teams=[1])

    api_client.cookies["current_team"] = "1"
    response = api_client.get("/api/v1/log/log_group/?page_size=-1")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()["data"]
    ids = {item["id"] for item in data}
    assert ids == {"g-1"}
    # 无显式 instance 权限时回落到默认权限
    assert data[0]["permission"]


@pytest.mark.django_db
def test_list_attaches_explicit_instance_permission(api_client, authenticated_user, mocker):
    LogGroup.objects.create(id="g-1", name="组1", rule={})
    LogGroupOrganization.objects.create(log_group_id="g-1", organization=1)
    _mock_permission(
        mocker,
        teams=[1],
        instance_permissions=[{"id": "g-1", "permission": ["View"]}],
    )

    api_client.cookies["current_team"] = "1"
    response = api_client.get("/api/v1/log/log_group/?page_size=-1")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()["data"]
    item = next(i for i in data if i["id"] == "g-1")
    assert item["permission"] == ["View"]


@pytest.mark.django_db
def test_list_paginated_default(api_client, authenticated_user, mocker):
    for idx in range(3):
        gid = f"p-{idx}"
        LogGroup.objects.create(id=gid, name=f"组{idx}", rule={})
        LogGroupOrganization.objects.create(log_group_id=gid, organization=1)
    _mock_permission(mocker, teams=[1])

    api_client.cookies["current_team"] = "1"
    response = api_client.get("/api/v1/log/log_group/")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    # 分页响应包含 count / items 结构
    assert "data" in body


@pytest.mark.django_db
def test_list_missing_team_returns_400(api_client, authenticated_user, mocker):
    _mock_permission(mocker, teams=[1])
    # 不设置 current_team cookie -> _get_current_team 抛 ValueError
    response = api_client.get("/api/v1/log/log_group/?page_size=-1")

    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_create_success_persists_group_and_organizations(api_client, authenticated_user, mocker):
    _mock_permission(mocker, teams=[1])

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/log/log_group/",
        data={"id": "new-group", "name": "新建组", "rule": {}, "organizations": [1]},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["data"]["id"] == "new-group"
    assert LogGroup.objects.filter(id="new-group").exists()
    assert LogGroupOrganization.objects.filter(log_group_id="new-group", organization=1).exists()
    # 创建者被记录
    assert LogGroup.objects.get(id="new-group").created_by == authenticated_user.username


@pytest.mark.django_db
def test_create_without_team_permission_returns_403(api_client, authenticated_user, mocker):
    _mock_permission(mocker, teams=[])

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/log/log_group/",
        data={"id": "x", "name": "x", "rule": {}},
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert not LogGroup.objects.filter(id="x").exists()


@pytest.mark.django_db
def test_create_with_unauthorized_organization_rejected(api_client, authenticated_user, mocker):
    _mock_permission(mocker, teams=[1])

    api_client.cookies["current_team"] = "1"
    response = api_client.post(
        "/api/v1/log/log_group/",
        data={"id": "y", "name": "y", "rule": {}, "organizations": [999]},
        format="json",
    )

    # 序列化器 validate_organizations 拒绝无权限组织
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert not LogGroup.objects.filter(id="y").exists()


@pytest.mark.django_db
def test_update_success_changes_name_and_orgs(api_client, authenticated_user, mocker):
    LogGroup.objects.create(id="u-1", name="旧名", rule={})
    LogGroupOrganization.objects.create(log_group_id="u-1", organization=1)
    _mock_permission(mocker, teams=[1])

    api_client.cookies["current_team"] = "1"
    response = api_client.put(
        "/api/v1/log/log_group/u-1/",
        data={"name": "新名", "rule": {}, "organizations": [1]},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert LogGroup.objects.get(id="u-1").name == "新名"
    assert LogGroup.objects.get(id="u-1").updated_by == authenticated_user.username


@pytest.mark.django_db
def test_update_denied_when_instance_lacks_operate(api_client, authenticated_user, mocker):
    LogGroup.objects.create(id="u-2", name="组", rule={})
    LogGroupOrganization.objects.create(log_group_id="u-2", organization=1)
    _mock_permission(
        mocker,
        teams=[1],
        instance_permissions=[{"id": "u-2", "permission": ["View"]}],
    )

    api_client.cookies["current_team"] = "1"
    response = api_client.put(
        "/api/v1/log/log_group/u-2/",
        data={"name": "尝试改名", "rule": {}},
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert LogGroup.objects.get(id="u-2").name == "组"


@pytest.mark.django_db
def test_destroy_success_removes_group_and_orgs(api_client, authenticated_user, mocker):
    LogGroup.objects.create(id="d-1", name="待删", rule={})
    LogGroupOrganization.objects.create(log_group_id="d-1", organization=1)
    _mock_permission(mocker, teams=[1])

    api_client.cookies["current_team"] = "1"
    response = api_client.delete("/api/v1/log/log_group/d-1/")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["data"]["name"] == "待删"
    assert not LogGroup.objects.filter(id="d-1").exists()
    assert not LogGroupOrganization.objects.filter(log_group_id="d-1").exists()


@pytest.mark.django_db
def test_destroy_denied_when_instance_lacks_operate(api_client, authenticated_user, mocker):
    LogGroup.objects.create(id="d-2", name="保护组", rule={})
    LogGroupOrganization.objects.create(log_group_id="d-2", organization=1)
    _mock_permission(
        mocker,
        teams=[1],
        instance_permissions=[{"id": "d-2", "permission": ["View"]}],
    )

    api_client.cookies["current_team"] = "1"
    response = api_client.delete("/api/v1/log/log_group/d-2/")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert LogGroup.objects.filter(id="d-2").exists()


@pytest.mark.django_db
def test_get_queryset_returns_none_when_team_missing(api_client, authenticated_user, mocker):
    """get_queryset 在权限解析失败（无 team cookie）时返回空集，retrieve 得到 404。"""
    LogGroup.objects.create(id="q-1", name="组", rule={})
    LogGroupOrganization.objects.create(log_group_id="q-1", organization=1)
    _mock_permission(mocker, teams=[1])

    # retrieve 走 get_queryset -> get_object，无 current_team 时返回 none -> 404
    response = api_client.get("/api/v1/log/log_group/q-1/")

    assert response.status_code == status.HTTP_404_NOT_FOUND
