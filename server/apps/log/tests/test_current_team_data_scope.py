import json
from types import SimpleNamespace

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.log.models import CollectInstance, CollectInstanceOrganization, CollectType
from apps.log.models.log_group import LogGroup, LogGroupOrganization
from apps.log.models.policy import Policy, PolicyOrganization
from apps.log.serializers.log_group import LogGroupSerializer
from apps.log.serializers.policy import PolicySerializer
from apps.log.services.access_scope import LogAccessScopeService
from apps.log.views.collect_config import CollectInstanceViewSet, CollectTypeViewSet
from apps.log.views.log_group import LogGroupViewSet
from apps.log.views.node import NodeViewSet
from apps.log.views.policy import PolicyViewSet
from apps.log.views.search import LogSearchViewSet

pytestmark = pytest.mark.django_db


def _patch_actor_scope(mocker, *, scoped_ids, assignable_ids=None):
    mocker.patch(
        "apps.core.utils.current_team_scope.SystemMgmt.get_authorized_groups_scoped",
        return_value={"result": True, "data": scoped_ids},
    )
    mocker.patch(
        "apps.core.utils.current_team_scope.SystemMgmt.get_assignable_groups",
        return_value={
            "result": True,
            "data": assignable_ids if assignable_ids is not None else scoped_ids,
        },
    )


def _request(*, current_team="1", is_superuser=True):
    return SimpleNamespace(
        COOKIES={"current_team": current_team, "include_children": "0"},
        user=SimpleNamespace(
            username="admin",
            domain="domain.com",
            group_list=[{"id": 1}, {"id": 2}],
            is_superuser=is_superuser,
        ),
    )


def test_superuser_log_group_scope_excludes_sibling_team(mocker):
    own = LogGroup.objects.create(id="scope-own", name="own", rule={})
    sibling = LogGroup.objects.create(id="scope-sibling", name="sibling", rule={})
    LogGroupOrganization.objects.create(log_group=own, organization=1)
    LogGroupOrganization.objects.create(log_group=sibling, organization=2)
    _patch_actor_scope(mocker, scoped_ids=[1])
    mocker.patch(
        "apps.log.services.access_scope.get_permission_rules",
        return_value={"team": [1, 2], "instance": []},
    )

    scope = LogAccessScopeService.resolve_scope(_request())

    assert scope.log_groups == [own.id]


def test_shared_log_group_response_projects_organizations_to_current_team(
    authenticated_user,
    mocker,
):
    authenticated_user.is_superuser = True
    authenticated_user.save(update_fields=["is_superuser"])
    shared = LogGroup.objects.create(id="shared", name="shared", rule={})
    LogGroupOrganization.objects.create(log_group=shared, organization=1)
    LogGroupOrganization.objects.create(log_group=shared, organization=2)
    _patch_actor_scope(mocker, scoped_ids=[1])
    mocker.patch(
        "apps.log.services.access_scope.get_permission_rules",
        return_value={"team": [1, 2], "instance": []},
    )
    request = APIRequestFactory().get("/api/v1/log/log_group/", {"page_size": "-1"})
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=authenticated_user)

    response = LogGroupViewSet.as_view({"get": "list"})(request)

    assert response.status_code == status.HTTP_200_OK
    assert json.loads(response.content)["data"][0]["organizations"] == [1]


def test_log_group_create_requires_organizations(mocker):
    request = _request(is_superuser=False)
    _patch_actor_scope(mocker, scoped_ids=[1], assignable_ids=[1, 2])
    serializer = LogGroupSerializer(
        data={"id": "missing-org", "name": "missing", "rule": {}},
        context={"request": request},
    )

    assert not serializer.is_valid()
    assert "organizations" in serializer.errors


def test_sibling_log_group_search_never_calls_victorialogs(
    authenticated_user,
    mocker,
):
    authenticated_user.is_superuser = True
    authenticated_user.save(update_fields=["is_superuser"])
    sibling = LogGroup.objects.create(id="search-sibling", name="sibling", rule={})
    LogGroupOrganization.objects.create(log_group=sibling, organization=2)
    _patch_actor_scope(mocker, scoped_ids=[1])
    mocker.patch(
        "apps.log.services.access_scope.get_permission_rules",
        return_value={"team": [1, 2], "instance": []},
    )
    external_query = mocker.patch(
        "apps.log.views.search.SearchService.search_logs",
        return_value=[],
    )
    request = APIRequestFactory().post(
        "/api/v1/log/search/search/",
        {"query": "*", "log_groups": [sibling.id]},
        format="json",
    )
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=authenticated_user)

    response = LogSearchViewSet.as_view({"post": "search"})(request)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    external_query.assert_not_called()


@pytest.mark.parametrize("current_team", ["01", "", "not-an-id"])
def test_invalid_current_team_search_never_calls_victorialogs(
    authenticated_user,
    mocker,
    current_team,
):
    authenticated_user.is_superuser = True
    authenticated_user.save(update_fields=["is_superuser"])
    group = LogGroup.objects.create(id=f"invalid-{current_team or 'empty'}", name="group", rule={})
    LogGroupOrganization.objects.create(log_group=group, organization=1)
    _patch_actor_scope(mocker, scoped_ids=[1])
    mocker.patch(
        "apps.log.services.access_scope.get_permission_rules",
        return_value={"team": [1], "instance": []},
    )
    external_query = mocker.patch(
        "apps.log.views.search.SearchService.search_logs",
        return_value=[],
    )
    request = APIRequestFactory().post(
        "/api/v1/log/search/search/",
        {"query": "*", "log_groups": [group.id]},
        format="json",
    )
    if current_team:
        request.COOKIES["current_team"] = current_team
    force_authenticate(request, user=authenticated_user)

    response = LogSearchViewSet.as_view({"post": "search"})(request)

    assert response.status_code in {status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN}
    external_query.assert_not_called()


def test_superuser_node_query_uses_current_team_scope(authenticated_user, mocker):
    authenticated_user.is_superuser = True
    authenticated_user.save(update_fields=["is_superuser"])
    _patch_actor_scope(mocker, scoped_ids=[1])
    node_mgmt = mocker.Mock()
    node_mgmt.node_list.return_value = {"count": 0, "nodes": []}
    mocker.patch("apps.log.views.node.NodeMgmt", return_value=node_mgmt)
    request = APIRequestFactory().post(
        "/api/v1/log/node_mgmt/nodes/",
        {"cloud_region_id": 1},
        format="json",
    )
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=authenticated_user)

    response = NodeViewSet.as_view({"post": "get_nodes"})(request)

    assert response.status_code == status.HTTP_200_OK
    assert node_mgmt.node_list.call_args.args[0]["organization_ids"] == [1]


def test_superuser_proxy_address_uses_current_team_scope(authenticated_user, mocker):
    authenticated_user.is_superuser = True
    authenticated_user.save(update_fields=["is_superuser"])
    _patch_actor_scope(mocker, scoped_ids=[1])
    node_mgmt = mocker.Mock()
    mocker.patch("apps.log.views.node.NodeMgmt", return_value=node_mgmt)
    resolve = mocker.patch(
        "apps.log.views.node.CloudRegionReceiverService.resolve",
        return_value="proxy.example.com",
    )
    request = APIRequestFactory().post(
        "/api/v1/log/node_mgmt/cloud_region_proxy_address/",
        {"cloud_region_id": 42},
        format="json",
    )
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=authenticated_user)

    response = NodeViewSet.as_view({"post": "get_cloud_region_proxy_address"})(request)

    assert response.status_code == status.HTTP_200_OK
    resolve.assert_called_once_with(node_mgmt, 42, [1])


@pytest.mark.parametrize(
    ("action", "path"),
    [
        ("get_nodes", "/api/v1/log/node_mgmt/nodes/"),
        (
            "get_cloud_region_proxy_address",
            "/api/v1/log/node_mgmt/cloud_region_proxy_address/",
        ),
    ],
)
def test_invalid_current_team_node_requests_fail_closed(
    authenticated_user,
    mocker,
    action,
    path,
):
    authenticated_user.is_superuser = True
    authenticated_user.save(update_fields=["is_superuser"])
    node_mgmt = mocker.patch("apps.log.views.node.NodeMgmt")
    request = APIRequestFactory().post(path, {}, format="json")
    request.COOKIES["current_team"] = "not-an-id"
    force_authenticate(request, user=authenticated_user)

    response = NodeViewSet.as_view({"post": action})(request)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    node_mgmt.assert_not_called()


def _policy(name):
    return Policy.objects.create(
        name=name,
        alert_type="keyword",
        alert_name=name,
        alert_level="warning",
    )


@pytest.mark.parametrize(
    ("organizations", "required", "expected", "has_error"),
    [
        ([], True, None, True),
        (None, False, [], False),
        (["1", 2, 1], False, [1, 2], False),
        ([True], False, None, True),
        (["01"], False, None, True),
        ("1", False, None, True),
    ],
)
def test_policy_organization_payload_requires_canonical_positive_ids(
    organizations,
    required,
    expected,
    has_error,
):
    normalized, response = PolicyViewSet._validate_organizations_payload(
        organizations,
        required=required,
    )

    assert normalized == expected
    assert (response is not None) is has_error


def test_superuser_policy_queryset_excludes_sibling_team(mocker):
    own = _policy("policy-own")
    sibling = _policy("policy-sibling")
    PolicyOrganization.objects.create(policy=own, organization=1)
    PolicyOrganization.objects.create(policy=sibling, organization=2)
    request = _request(is_superuser=True)
    _patch_actor_scope(mocker, scoped_ids=[1], assignable_ids=[1, 2])
    mocker.patch(
        "apps.log.views.policy.get_permissions_rules",
        return_value={
            "data": {"all": {"team": [1, 2]}},
            "team": [1, 2],
        },
    )

    queryset, _ = PolicyViewSet()._get_accessible_policy_queryset(request)

    assert list(queryset.values_list("id", flat=True)) == [own.id]


def test_policy_allows_assignable_sibling_target(mocker):
    request = _request(is_superuser=False)
    _patch_actor_scope(mocker, scoped_ids=[1], assignable_ids=[1, 2])
    mocker.patch(
        "apps.log.views.policy.get_permissions_rules",
        return_value={"data": {}, "team": [1]},
    )

    response = PolicyViewSet()._authorize_target_organizations(request, [2])

    assert response is None


def test_policy_rejects_explicit_empty_organizations(mocker):
    request = _request(is_superuser=False)
    _patch_actor_scope(mocker, scoped_ids=[1], assignable_ids=[1, 2])

    response = PolicyViewSet()._authorize_target_organizations(request, [])

    assert response is not None
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_shared_policy_response_projects_organizations_to_current_team(mocker):
    shared = _policy("policy-shared")
    PolicyOrganization.objects.create(policy=shared, organization=1)
    PolicyOrganization.objects.create(policy=shared, organization=2)
    request = _request(is_superuser=True)
    _patch_actor_scope(mocker, scoped_ids=[1], assignable_ids=[1, 2])

    data = PolicySerializer(
        shared,
        context={"request": request, "data_team_ids": frozenset({1})},
    ).data

    assert data["organizations"] == [1]


@pytest.mark.parametrize("include_collect_type", [True, False])
def test_shared_collect_instance_response_projects_organizations_to_current_team(
    authenticated_user,
    mocker,
    include_collect_type,
):
    authenticated_user.is_superuser = True
    authenticated_user.save(update_fields=["is_superuser"])
    collect_type = CollectType.objects.create(
        name=f"projection-{include_collect_type}",
        collector="Filebeat",
        icon="",
    )
    instance = CollectInstance.objects.create(
        id=f"shared-instance-{include_collect_type}",
        name="shared instance",
        collect_type=collect_type,
    )
    CollectInstanceOrganization.objects.bulk_create(
        [
            CollectInstanceOrganization(
                collect_instance=instance,
                organization=1,
            ),
            CollectInstanceOrganization(
                collect_instance=instance,
                organization=2,
            ),
        ]
    )
    _patch_actor_scope(mocker, scoped_ids=[1])
    payload = {"page": 1, "page_size": 10}
    if include_collect_type:
        payload["collect_type_id"] = collect_type.id
    request = APIRequestFactory().post(
        "/api/v1/log/collect_instances/search/",
        payload,
        format="json",
    )
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=authenticated_user)

    response = CollectInstanceViewSet.as_view({"post": "search"})(request)

    assert response.status_code == status.HTTP_200_OK
    items = json.loads(response.content)["data"]["items"]
    assert items[0]["organization"] == [1]


def _list_collect_types_with_count(
    authenticated_user,
    mocker,
    query_param,
):
    authenticated_user.is_superuser = False
    authenticated_user.save(update_fields=["is_superuser"])
    _patch_actor_scope(mocker, scoped_ids=[1])
    mocker.patch(
        "apps.log.views.collect_config.get_permissions_rules",
        return_value={
            "data": {"all": {"team": [1, 2]}},
            "team": [1, 2],
        },
    )
    language = mocker.patch("apps.log.views.collect_config.LanguageLoader").return_value
    language.get.return_value = None
    request = APIRequestFactory().get(
        "/api/v1/log/collect_types/",
        {query_param: "true"},
    )
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=authenticated_user)
    return CollectTypeViewSet.as_view({"get": "list"})(request)


def test_policy_count_intersects_permission_with_current_team(
    authenticated_user,
    mocker,
):
    collect_type = CollectType.objects.create(
        name="policy-count-scope",
        collector="Filebeat",
        icon="",
    )
    own = _policy("policy-count-own")
    own.collect_type = collect_type
    own.save(update_fields=["collect_type"])
    sibling = _policy("policy-count-sibling")
    sibling.collect_type = collect_type
    sibling.save(update_fields=["collect_type"])
    PolicyOrganization.objects.create(policy=own, organization=1)
    PolicyOrganization.objects.create(policy=sibling, organization=2)

    response = _list_collect_types_with_count(
        authenticated_user,
        mocker,
        "add_policy_count",
    )

    assert response.status_code == status.HTTP_200_OK
    item = next(item for item in json.loads(response.content)["data"] if item["id"] == collect_type.id)
    assert item["policy_count"] == 1


def test_instance_count_intersects_permission_with_current_team(
    authenticated_user,
    mocker,
):
    collect_type = CollectType.objects.create(
        name="instance-count-scope",
        collector="Filebeat",
        icon="",
    )
    own = CollectInstance.objects.create(
        id="instance-count-own",
        name="own",
        collect_type=collect_type,
    )
    sibling = CollectInstance.objects.create(
        id="instance-count-sibling",
        name="sibling",
        collect_type=collect_type,
    )
    CollectInstanceOrganization.objects.create(
        collect_instance=own,
        organization=1,
    )
    CollectInstanceOrganization.objects.create(
        collect_instance=sibling,
        organization=2,
    )

    response = _list_collect_types_with_count(
        authenticated_user,
        mocker,
        "add_instance_count",
    )

    assert response.status_code == status.HTTP_200_OK
    item = next(item for item in json.loads(response.content)["data"] if item["id"] == collect_type.id)
    assert item["instance_count"] == 1


def test_policy_create_allows_assignable_sibling_and_projects_response(
    authenticated_user,
    mocker,
):
    authenticated_user.is_superuser = False
    authenticated_user.save(update_fields=["is_superuser"])
    _patch_actor_scope(mocker, scoped_ids=[1], assignable_ids=[1, 2])
    mocker.patch(
        "apps.log.views.policy.get_permissions_rules",
        return_value={"data": {}, "team": [1]},
    )
    mocker.patch.object(PolicyViewSet, "update_or_create_task")
    request = APIRequestFactory().post(
        "/api/v1/log/policy/",
        {
            "name": "assignable-sibling-policy",
            "alert_type": "keyword",
            "alert_name": "assignable sibling",
            "alert_level": "warning",
            "alert_condition": {"query": "error"},
            "schedule": {"type": "min", "value": 5},
            "period": {"type": "min", "value": 5},
            "organizations": [2],
        },
        format="json",
    )
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=authenticated_user)

    response = PolicyViewSet.as_view({"post": "create"})(request)

    assert response.status_code == status.HTTP_201_CREATED
    policy = Policy.objects.get(name="assignable-sibling-policy")
    assert list(policy.policyorganization_set.values_list("organization", flat=True)) == [2]
    assert response.data["organizations"] == []


@pytest.mark.parametrize("partial", [False, True])
def test_log_group_update_without_organizations_preserves_binding(
    mocker,
    partial,
):
    group = LogGroup.objects.create(
        id=f"preserve-{partial}",
        name="before",
        rule={},
    )
    LogGroupOrganization.objects.create(log_group=group, organization=1)
    request = _request(is_superuser=False)
    _patch_actor_scope(mocker, scoped_ids=[1], assignable_ids=[1, 2])
    serializer = LogGroupSerializer(
        group,
        data={"name": "after", "rule": {}},
        partial=partial,
        context={"request": request},
    )

    assert serializer.is_valid(), serializer.errors
    serializer.save()

    assert list(group.loggrouporganization_set.values_list("organization", flat=True)) == [1]


@pytest.mark.parametrize(
    "organizations",
    [
        [],
        [True],
        [1.0],
        ["01"],
        [0],
        [-1],
    ],
)
def test_log_group_rejects_empty_or_noncanonical_organization_ids(
    mocker,
    organizations,
):
    request = _request(is_superuser=False)
    _patch_actor_scope(mocker, scoped_ids=[1], assignable_ids=[1, 2])
    serializer = LogGroupSerializer(
        data={
            "id": f"invalid-org-{organizations!s}",
            "name": "invalid organizations",
            "rule": {},
            "organizations": organizations,
        },
        context={"request": request},
    )

    assert not serializer.is_valid()
    assert "organizations" in serializer.errors


def test_log_group_accepts_canonical_integer_and_numeric_string_ids(mocker):
    request = _request(is_superuser=False)
    _patch_actor_scope(mocker, scoped_ids=[1], assignable_ids=[1, 2])
    serializer = LogGroupSerializer(
        data={
            "id": "canonical-organizations",
            "name": "canonical organizations",
            "rule": {},
            "organizations": ["1", 2],
        },
        context={"request": request},
    )

    assert serializer.is_valid(), serializer.errors
    group = serializer.save()
    assert list(
        group.loggrouporganization_set.order_by("organization").values_list(
            "organization",
            flat=True,
        )
    ) == [1, 2]
