import json

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.views.instance import InstanceViewSet


VIEWS = "apps.cmdb.views.instance"


@pytest.fixture
def superuser(authenticated_user):
    authenticated_user.is_superuser = True
    authenticated_user.group_list = [{"id": 1}]
    authenticated_user.group_tree = []
    authenticated_user.roles = ["admin"]
    return authenticated_user


def request(user, **query):
    req = APIRequestFactory().get("/x/", data=query)
    req.COOKIES["current_team"] = "1"
    force_authenticate(req, user=user)
    return req


def body(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


@pytest.fixture(autouse=True)
def instance_guards(monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_id",
        lambda inst_id: {"_id": int(inst_id), "model_id": "k8s_cluster", "inst_name": "prod"},
    )
    monkeypatch.setattr(
        f"{VIEWS}.InstanceViewSet.require_instance_permission",
        lambda self, req, instance, operator=None: None,
    )


@pytest.mark.django_db
def test_overview_action_builds_permission_map_for_each_child_model(superuser, monkeypatch):
    captured = {}

    monkeypatch.setattr(
        f"{VIEWS}.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda request, model_id, permission_type=None: {"model": model_id},
    )
    monkeypatch.setattr(
        f"{VIEWS}.K8sResourceOverviewService.get_overview",
        lambda cluster_id, permission_maps=None, user=None: captured.update(permission_maps=permission_maps) or {"summary": {}},
    )

    response = InstanceViewSet.as_view({"get": "k8s_resource_overview"})(request(superuser), cluster_id="1")

    assert response.status_code == status.HTTP_200_OK
    assert set(captured["permission_maps"]) == {"k8s_namespace", "k8s_workload", "k8s_pod", "k8s_node"}


@pytest.mark.django_db
def test_layer_action_validates_limits_and_namespace_ids(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda request, model_id, permission_type=None: {},
    )
    monkeypatch.setattr(
        f"{VIEWS}.K8sResourceOverviewService.get_layer",
        lambda cluster_id, layer, **kwargs: {"layer": layer, "namespace_ids": kwargs["namespace_ids"]},
    )

    response = InstanceViewSet.as_view({"get": "k8s_resource_layer"})(
        request(superuser, page="2", page_size="50", namespace_ids="10,11"),
        cluster_id="1",
        layer="workload",
    )

    assert response.status_code == status.HTTP_200_OK
    assert body(response)["data"] == {"layer": "workload", "namespace_ids": [10, 11]}


@pytest.mark.django_db
def test_workload_pods_action_caps_page_size_at_fifty(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda request, model_id, permission_type=None: {},
    )
    response = InstanceViewSet.as_view({"get": "k8s_workload_pods"})(
        request(superuser, page_size="51"), cluster_id="1", workload_id="20"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_resource_list_action_passes_read_only_filters(superuser, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        f"{VIEWS}.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda request, model_id, permission_type=None: {},
    )
    monkeypatch.setattr(
        f"{VIEWS}.K8sResourceOverviewService.list_resources",
        lambda cluster_id, kind, **kwargs: captured.update(kind=kind, **kwargs) or {"items": [], "count": 0},
    )

    response = InstanceViewSet.as_view({"get": "k8s_resource_list"})(
        request(superuser, search="api", order="-name", namespace_id="10"),
        cluster_id="1",
        kind="deployment",
    )

    assert response.status_code == status.HTTP_200_OK
    assert captured["kind"] == "deployment"
    assert captured["search"] == "api"
    assert captured["order"] == "-name"
    assert captured["namespace_id"] == 10


@pytest.mark.django_db
def test_unowned_pods_action_is_read_only_get(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda request, model_id, permission_type=None: {},
    )
    monkeypatch.setattr(
        f"{VIEWS}.K8sResourceOverviewService.get_unowned_pods",
        lambda cluster_id, **kwargs: {"items": [], "count": 0},
    )

    response = InstanceViewSet.as_view({"get": "k8s_unowned_pods"})(
        request(superuser), cluster_id="1"
    )

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_k8s_actions_reject_non_cluster_instance(superuser, monkeypatch):
    monkeypatch.setattr(
        f"{VIEWS}.InstanceManage.query_entity_by_id",
        lambda inst_id: {"_id": int(inst_id), "model_id": "host", "inst_name": "host-a"},
    )

    response = InstanceViewSet.as_view({"get": "k8s_resource_overview"})(request(superuser), cluster_id="1")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "k8s_cluster" in str(body(response))
