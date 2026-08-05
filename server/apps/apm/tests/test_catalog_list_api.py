from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.apm.models import ApmServiceInstance
from apps.apm.services import DjangoTelemetryCatalogService
from apps.apm.services.contracts import CatalogDiscovery
from apps.apm.tests.helpers import create_application

pytestmark = pytest.mark.django_db


def _discover(
    namespace: str,
    service_name: str,
    instance_id: str,
    environment: str,
    *,
    seen_at,
):
    return DjangoTelemetryCatalogService().discover(CatalogDiscovery(namespace, service_name, instance_id, environment, seen_at=seen_at))


@pytest.fixture
def catalog_rows():
    now = timezone.now()
    create_application("shop", (10,))
    create_application("billing", (10,))
    create_application("hidden", (20,))

    active = _discover("shop", "checkout-api", "pod-active", "prod", seen_at=now - timedelta(minutes=1))
    billing = _discover("billing", "invoice-api", "pod-billing", "stage", seen_at=now - timedelta(minutes=2))
    silent = _discover("shop", "checkout-api", "pod-silent", "dev", seen_at=now - timedelta(hours=1))
    archived = _discover("shop", "checkout-api", "pod-archived", "prod", seen_at=now - timedelta(days=10))
    hidden = _discover("hidden", "private-api", "pod-hidden", "prod", seen_at=now)
    ApmServiceInstance.objects.filter(id=archived.instance.id).update(archived_at=now, archive_reason="silent_timeout")
    return {
        "now": now,
        "active": active,
        "billing": billing,
        "silent": silent,
        "archived": archived,
        "hidden": hidden,
    }


def test_instance_list_keeps_legacy_array_but_supports_bounded_pagination(apm_api_client, catalog_rows):
    legacy = apm_api_client.get("/api/v1/apm/instances/")
    paged = apm_api_client.get("/api/v1/apm/instances/", {"page": 1, "page_size": 2})

    assert legacy.status_code == paged.status_code == 200
    assert isinstance(legacy.data, list)
    assert paged.data["count"] == 3
    assert len(paged.data["items"]) == 2
    assert [item["last_seen_at"] for item in paged.data["items"]] == sorted(
        (item["last_seen_at"] for item in paged.data["items"]),
        reverse=True,
    )
    assert all(item["application_id"] != "hidden" for item in paged.data["items"])


def test_instance_list_filters_application_environment_status_time_and_keyword_on_server(apm_api_client, catalog_rows):
    now = catalog_rows["now"]
    response = apm_api_client.get(
        "/api/v1/apm/instances/",
        {
            "page_size": 20,
            "application": "shop",
            "environment": "prod",
            "status": "active",
            "started_at": (now - timedelta(minutes=5)).isoformat(),
            "ended_at": now.isoformat(),
            "keyword": "CHECKOUT pod-active",
        },
    )

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["items"][0]["id"] == str(catalog_rows["active"].instance.id)


@pytest.mark.parametrize(
    "params",
    [
        {"page_size": 20, "status": "unknown"},
        {"page_size": 20, "started_at": "not-a-date"},
        {"page_size": 0},
        {"page_size": -1},
        {"page_size": 20, "page": 0},
        {
            "page_size": 20,
            "started_at": "2026-08-05T12:00:00Z",
            "ended_at": "2026-08-05T11:00:00Z",
        },
    ],
)
def test_instance_list_rejects_invalid_filters(apm_api_client, params):
    response = apm_api_client.get("/api/v1/apm/instances/", params)

    assert response.status_code == 400


def test_service_list_pagination_and_filters_are_optional_and_compatible(apm_api_client, catalog_rows):
    legacy = apm_api_client.get("/api/v1/apm/services/")
    paged = apm_api_client.get(
        "/api/v1/apm/services/",
        {"page_size": 1, "application": "shop", "status": "active", "keyword": "checkout"},
    )

    assert isinstance(legacy.data, list)
    assert paged.status_code == 200
    assert paged.data["count"] == 1
    assert paged.data["items"][0]["application_id"] == "shop"
    assert paged.data["items"][0]["name"] == "checkout-api"


def test_catalog_page_size_is_capped_for_public_list_queries(apm_api_client, catalog_rows):
    for index in range(101):
        _discover(
            "shop",
            "bulk-api",
            f"pod-{index:03d}",
            "prod",
            seen_at=catalog_rows["now"] - timedelta(seconds=index),
        )
    response = apm_api_client.get("/api/v1/apm/instances/", {"page_size": 1000})

    assert response.status_code == 200
    assert response.data["count"] == 104
    assert len(response.data["items"]) == 100


def test_paginated_instance_list_requires_directory_permission(apm_user_without_permissions):
    client = APIClient()
    client.force_authenticate(user=apm_user_without_permissions)
    client.cookies["current_team"] = "10"

    response = client.get("/api/v1/apm/instances/", {"page_size": 20, "status": "active"})

    assert response.status_code == 403


def test_instance_directory_permission_can_read_application_filter_options(apm_user):
    client = APIClient()
    client.force_authenticate(user=apm_user)
    client.cookies["current_team"] = "10"
    apm_user.permission["apm"] = {"integration_instances-View"}

    response = client.get("/api/v1/apm/applications/")

    assert response.status_code == 200
