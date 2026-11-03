"""目录重挂的真实 DRF 接口契约。"""

import json

import pytest
from django.test import override_settings
from django.urls import path
from rest_framework import status

from apps.operation_analysis.models.models import Directory
from apps.operation_analysis.views import view as view_module

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

urlpatterns = [
    path(
        "api/directory/<int:pk>/",
        view_module.DirectoryModelViewSet.as_view({"patch": "partial_update"}),
        name="test-directory-detail",
    )
]


def _make_superuser(user):
    user.is_superuser = True
    return user


@override_settings(ROOT_URLCONF=__name__, MIDDLEWARE=())
def test_directory_partial_update_rejects_parent_cycle(api_client, authenticated_user):
    _make_superuser(authenticated_user)
    root = Directory.objects.create(name="根目录", groups=[1], created_by="testuser")
    child = Directory.objects.create(name="子目录", groups=[1], parent=root, created_by="testuser")

    response = api_client.patch(f"/api/directory/{root.id}/", {"parent": child.id}, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "cannot contain cycles" in json.dumps(response.json(), ensure_ascii=False)
    root.refresh_from_db()
    assert root.parent_id is None


@override_settings(ROOT_URLCONF=__name__, MIDDLEWARE=())
def test_directory_partial_update_rejects_self_parent(api_client, authenticated_user):
    _make_superuser(authenticated_user)
    directory = Directory.objects.create(name="自指目录", groups=[1], created_by="testuser")

    response = api_client.patch(f"/api/directory/{directory.id}/", {"parent": directory.id}, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "cannot contain cycles" in json.dumps(response.json(), ensure_ascii=False)
    directory.refresh_from_db()
    assert directory.parent_id is None


@override_settings(ROOT_URLCONF=__name__, MIDDLEWARE=())
def test_directory_partial_update_persists_valid_reparenting(api_client, authenticated_user):
    _make_superuser(authenticated_user)
    first_root = Directory.objects.create(name="原父目录", groups=[1], created_by="testuser")
    second_root = Directory.objects.create(name="新父目录", groups=[1], created_by="testuser")
    child = Directory.objects.create(name="待重挂目录", groups=[1], parent=first_root, created_by="testuser")

    response = api_client.patch(f"/api/directory/{child.id}/", {"parent": second_root.id}, format="json")

    assert response.status_code == status.HTTP_200_OK
    child.refresh_from_db()
    assert child.parent_id == second_root.id


@override_settings(ROOT_URLCONF=__name__, MIDDLEWARE=())
def test_directory_partial_update_rejects_reparent_that_makes_descendant_exceed_three_levels(api_client, authenticated_user):
    _make_superuser(authenticated_user)
    directory_a = Directory.objects.create(name="目录A", groups=[1], created_by="testuser")
    directory_b = Directory.objects.create(name="目录B", groups=[1], parent=directory_a, created_by="testuser")
    directory_c = Directory.objects.create(name="目录C", groups=[1], parent=directory_b, created_by="testuser")
    directory_x = Directory.objects.create(name="目录X", groups=[1], created_by="testuser")

    response = api_client.patch(f"/api/directory/{directory_a.id}/", {"parent": directory_x.id}, format="json")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Directory hierarchy cannot exceed 3 levels" in json.dumps(response.json(), ensure_ascii=False)
    directory_a.refresh_from_db()
    directory_b.refresh_from_db()
    directory_c.refresh_from_db()
    assert directory_a.parent_id is None
    assert directory_b.parent_id == directory_a.id
    assert directory_c.parent_id == directory_b.id


@override_settings(ROOT_URLCONF=__name__, MIDDLEWARE=())
def test_directory_partial_update_allows_two_level_subtree_reparent(api_client, authenticated_user):
    _make_superuser(authenticated_user)
    directory_a = Directory.objects.create(name="两级根", groups=[1], created_by="testuser")
    directory_b = Directory.objects.create(name="两级子", groups=[1], parent=directory_a, created_by="testuser")
    directory_x = Directory.objects.create(name="两级新根", groups=[1], created_by="testuser")

    response = api_client.patch(f"/api/directory/{directory_a.id}/", {"parent": directory_x.id}, format="json")

    assert response.status_code == status.HTTP_200_OK
    directory_a.refresh_from_db()
    directory_b.refresh_from_db()
    assert directory_a.parent_id == directory_x.id
    assert directory_b.parent_id == directory_a.id
