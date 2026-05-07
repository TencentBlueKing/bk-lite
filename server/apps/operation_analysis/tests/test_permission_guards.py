from unittest.mock import patch

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.base.models import User
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, NameSpace
from apps.operation_analysis.models.models import Dashboard
from apps.operation_analysis.views.datasource_view import DataSourceAPIModelViewSet, NameSpaceModelViewSet
from apps.operation_analysis.views.import_export_view import ImportExportViewSet
from apps.operation_analysis.views.openapi_import_export_view import OpenImportExportViewSet
from apps.operation_analysis.views.view import DirectoryModelViewSet


pytestmark = pytest.mark.django_db


def _set_permissions(user, *permissions):
    user.permission = {"ops-analysis": set(permissions)}
    return user


def _create_user(username, group_list):
    return User.objects.create_user(
        username=username,
        password="testpass123",
        domain="domain.com",
        locale="en",
        group_list=group_list,
        roles=[],
    )


def test_get_source_data_rejects_datasource_outside_authorized_scope():
    factory = APIRequestFactory()
    user = _set_permissions(
        _create_user("viewer", [{"id": 1, "name": "Team 1"}]),
        "data_source-View",
    )
    namespace = NameSpace.objects.create(name="ns-1", namespace="bk", account="user", password="secret", domain="nats.example.com")
    datasource = DataSourceAPIModel.objects.create(
        name="ds-1",
        rest_api="ops/query",
        groups=[2],
        created_by="other",
        updated_by="other",
        domain="domain.com",
        updated_by_domain="domain.com",
    )
    datasource.namespaces.add(namespace)

    request = factory.post(f"/api/v1/operation_analysis/api/data_source/get_source_data/{datasource.id}/", {}, format="json")
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)

    view = DataSourceAPIModelViewSet.as_view({"post": "get_source_data"})
    with patch("apps.operation_analysis.services.access_control.get_permission_rules", return_value={"team": [], "instance": []}), patch(
        "apps.operation_analysis.views.datasource_view.GetNatsData.get_data"
    ) as mocked_get_data:
        response = view(request, pk=str(datasource.id))

    assert response.status_code == 403
    mocked_get_data.assert_not_called()


def test_namespace_list_only_returns_namespaces_bound_to_authorized_datasources():
    factory = APIRequestFactory()
    user = _set_permissions(
        _create_user("viewer-list", [{"id": 1, "name": "Team 1"}]),
        "namespace-View",
    )
    visible_ns = NameSpace.objects.create(name="visible-ns", namespace="bk", account="user", password="secret", domain="nats-visible.example.com")
    hidden_ns = NameSpace.objects.create(name="hidden-ns", namespace="bk", account="user", password="secret", domain="nats-hidden.example.com")
    visible_ds = DataSourceAPIModel.objects.create(
        name="visible-ds",
        rest_api="ops/visible",
        groups=[1],
        created_by="other",
        updated_by="other",
        domain="domain.com",
        updated_by_domain="domain.com",
    )
    hidden_ds = DataSourceAPIModel.objects.create(
        name="hidden-ds",
        rest_api="ops/hidden",
        groups=[2],
        created_by="other",
        updated_by="other",
        domain="domain.com",
        updated_by_domain="domain.com",
    )
    visible_ds.namespaces.add(visible_ns)
    hidden_ds.namespaces.add(hidden_ns)

    request = factory.get("/api/v1/operation_analysis/api/namespace/")
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)

    view = NameSpaceModelViewSet.as_view({"get": "list"})
    with patch(
        "apps.operation_analysis.views.datasource_view.build_authorized_queryset",
        return_value=DataSourceAPIModel.objects.filter(id=visible_ds.id),
    ):
        response = view(request)

    assert response.status_code == 200
    assert [item["name"] for item in response.data] == ["visible-ns"]


def test_export_rejects_dashboard_ids_outside_authorized_scope():
    factory = APIRequestFactory()
    user = _set_permissions(
        _create_user("viewer-export", [{"id": 1, "name": "Team 1"}]),
        "operation_analysis-View",
    )
    dashboard = Dashboard.objects.create(
        name="cross-team-dashboard",
        groups=[2],
        created_by="other",
        updated_by="other",
        domain="domain.com",
        updated_by_domain="domain.com",
    )

    request = factory.post(
        "/api/v1/operation_analysis/api/import_export/export/",
        {"object_type": "dashboard", "object_ids": [dashboard.id]},
        format="json",
    )
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)

    view = ImportExportViewSet.as_view({"post": "export_objects"})
    with patch("apps.operation_analysis.services.access_control.get_permission_rules", return_value={"team": [], "instance": []}), patch(
        "apps.operation_analysis.views.import_export_view.ExportService.export_objects"
    ) as mocked_export:
        response = view(request)

    assert response.status_code == 403
    mocked_export.assert_not_called()


def test_openapi_export_rejects_dashboard_ids_outside_token_team_scope():
    factory = APIRequestFactory()
    user = _create_user("api-user", [1])
    dashboard = Dashboard.objects.create(
        name="cross-team-openapi-dashboard",
        groups=[2],
        created_by="other",
        updated_by="other",
        domain="domain.com",
        updated_by_domain="domain.com",
    )

    request = factory.post(
        "/api/v1/operation_analysis/open_api/import_export/export",
        {"object_type": "dashboard", "object_ids": [dashboard.id]},
        format="json",
    )
    request.api_pass = True
    force_authenticate(request, user=user)

    view = OpenImportExportViewSet.as_view({"post": "export_objects"})
    with patch("apps.operation_analysis.services.access_control.get_permission_rules", return_value={"team": [], "instance": []}), patch(
        "apps.operation_analysis.views.openapi_import_export_view.ExportService.export_objects"
    ) as mocked_export:
        response = view(request)

    assert response.status_code == 400
    mocked_export.assert_not_called()


def test_directory_tree_requires_view_permission():
    factory = APIRequestFactory()
    user = _set_permissions(_create_user("tree-user", [{"id": 1, "name": "Team 1"}]))

    request = factory.get("/api/v1/operation_analysis/api/directory/tree/")
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)

    view = DirectoryModelViewSet.as_view({"get": "tree"})
    with patch("apps.operation_analysis.views.view.DictDirectoryService.get_dict_trees") as mocked_get_tree:
        response = view(request)

    assert response.status_code == 403
    mocked_get_tree.assert_not_called()
