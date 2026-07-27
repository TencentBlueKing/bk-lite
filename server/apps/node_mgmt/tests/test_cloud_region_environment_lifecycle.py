import pytest
from types import SimpleNamespace
from unittest.mock import patch
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.node_mgmt.constants.cloudregion_service import CloudRegionServiceConstants
from apps.node_mgmt.constants.database import CloudRegionConstants
from apps.node_mgmt.models.cloud_region import CloudRegion, CloudRegionService
from apps.node_mgmt.serializers.cloud_region import (
    CloudRegionProxyAddressSerializer,
    CloudRegionSerializer,
)
from apps.node_mgmt.services.cloudregion import RegionService
from apps.node_mgmt.views.cloud_region import CloudRegionViewSet


def _add_service(region, name, *, deployed, status):
    return CloudRegionService.objects.create(
        cloud_region=region,
        name=name,
        deployed_status=(
            CloudRegionServiceConstants.DEPLOYED
            if deployed
            else CloudRegionServiceConstants.NOT_DEPLOYED_STATUS
        ),
        status=status,
    )


@pytest.mark.django_db
def test_default_region_is_system_managed():
    region, _ = CloudRegion.objects.update_or_create(
        id=CloudRegionConstants.DEFAULT_CLOUD_REGION_ID,
        defaults={"name": "default"},
    )
    for name in CloudRegionServiceConstants.SERVICES:
        _add_service(
            region,
            name,
            deployed=True,
            status=CloudRegionServiceConstants.NORMAL,
        )

    payload = CloudRegionSerializer(region).data

    assert payload["is_default"] is True
    assert payload["deployment_state"] == "system_managed"
    assert payload["health_state"] == "normal"


@pytest.mark.django_db
def test_user_managed_region_reports_deployment_and_health_separately():
    region = CloudRegion.objects.create(name="lifecycle-region")
    _add_service(
        region,
        CloudRegionServiceConstants.STARGAZER_SERVICE_NAME,
        deployed=True,
        status=CloudRegionServiceConstants.NORMAL,
    )
    _add_service(
        region,
        CloudRegionServiceConstants.NATS_EXECUTOR_SERVICE_NAME,
        deployed=False,
        status=CloudRegionServiceConstants.N_ERROR,
    )

    payload = CloudRegionSerializer(region).data

    assert payload["is_default"] is False
    assert payload["deployment_state"] == "partially_deployed"
    assert payload["health_state"] == "abnormal"
    by_name = {service["name"]: service for service in payload["services"]}
    assert by_name[CloudRegionServiceConstants.STARGAZER_SERVICE_NAME]["deployment_status"] == "deployed"
    assert by_name[CloudRegionServiceConstants.STARGAZER_SERVICE_NAME]["health_status"] == "normal"
    assert by_name[CloudRegionServiceConstants.NATS_EXECUTOR_SERVICE_NAME]["deployment_status"] == "not_deployed"
    assert by_name[CloudRegionServiceConstants.NATS_EXECUTOR_SERVICE_NAME]["health_status"] == "unknown"


@pytest.mark.django_db
def test_missing_required_service_cannot_report_deployed_and_healthy():
    region = CloudRegion.objects.create(name="missing-required-service")
    _add_service(
        region,
        CloudRegionServiceConstants.STARGAZER_SERVICE_NAME,
        deployed=True,
        status=CloudRegionServiceConstants.NORMAL,
    )

    payload = CloudRegionSerializer(region).data

    assert payload["deployment_state"] == "partially_deployed"
    assert payload["health_state"] == "abnormal"


@pytest.mark.django_db
def test_default_region_cannot_be_deleted_through_the_api():
    region, _ = CloudRegion.objects.update_or_create(
        id=CloudRegionConstants.DEFAULT_CLOUD_REGION_ID,
        defaults={"name": "default"},
    )
    request = APIRequestFactory().delete(
        f"/node_mgmt/api/cloud_region/{region.id}/"
    )
    force_authenticate(
        request,
        user=SimpleNamespace(is_superuser=True, is_authenticated=True),
    )
    view = CloudRegionViewSet.as_view({"delete": "destroy"})

    with pytest.raises(BaseAppException, match="默认云区域"):
        view(request, pk=str(region.id))


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("method_name", "kwargs"),
    [
        ("stage_proxy_address", {"proxy_address": "proxy.example.com"}),
        ("cancel_pending_proxy_address", {}),
        ("activate_pending_proxy_address", {"confirmed": True}),
    ],
)
def test_default_region_rejects_proxy_lifecycle_operations(
    method_name,
    kwargs,
):
    region, _ = CloudRegion.objects.update_or_create(
        id=CloudRegionConstants.DEFAULT_CLOUD_REGION_ID,
        defaults={"name": "default"},
    )

    with pytest.raises(BaseAppException, match="默认云区域"):
        getattr(RegionService, method_name)(region.id, **kwargs)


@pytest.mark.django_db
def test_first_deployment_proxy_update_rolls_back_when_env_sync_fails():
    region = CloudRegion.objects.create(
        name="atomic-first-deployment",
        proxy_address="old.proxy.example.com",
    )
    request = APIRequestFactory().patch(
        f"/node_mgmt/api/cloud_region/{region.id}/",
        {"proxy_address": "new.proxy.example.com"},
        format="json",
    )
    force_authenticate(
        request,
        user=SimpleNamespace(is_superuser=True, is_authenticated=True),
    )
    view = CloudRegionViewSet.as_view({"patch": "partial_update"})

    with patch.object(
        RegionService,
        "sync_proxy_related_env_vars",
        side_effect=RuntimeError("sync failed"),
    ), pytest.raises(RuntimeError, match="sync failed"):
        view(request, pk=str(region.id))

    region.refresh_from_db()
    assert region.proxy_address == "old.proxy.example.com"


@pytest.mark.parametrize(
    ("proxy_address", "is_valid"),
    [
        ("10.0.0.8", True),
        ("proxy.example.com", True),
        ("2001:db8::8", True),
        ("https://proxy.example.com", False),
        ("not-a-host", False),
    ],
)
def test_proxy_address_accepts_only_ip_or_domain(proxy_address, is_valid):
    serializer = CloudRegionProxyAddressSerializer(
        data={"proxy_address": proxy_address}
    )

    assert serializer.is_valid() is is_valid


@pytest.mark.django_db
def test_create_payload_cannot_set_pending_proxy_state():
    serializer = CloudRegionSerializer(
        data={
            "name": "api-created-region",
            "pending_proxy_address": "proxy.example.com\nsubjectAltName=DNS:injected",
            "pending_proxy_address_created_at": "2026-07-27T00:00:00Z",
        }
    )

    assert serializer.is_valid(), serializer.errors
    assert "pending_proxy_address" not in serializer.validated_data
    assert "pending_proxy_address_created_at" not in serializer.validated_data


@pytest.mark.django_db
def test_environment_editor_can_generate_deploy_script():
    region = CloudRegion.objects.create(name="permission-region")
    request = APIRequestFactory().post(
        "/node_mgmt/api/cloud_region/deploy_command/",
        {"cloud_region_id": region.id},
        format="json",
    )
    force_authenticate(
        request,
        user=SimpleNamespace(
            is_superuser=False,
            is_authenticated=True,
            locale="zh-Hans",
            permission={"node": {"cloud_region_environment-Edit"}},
        ),
    )
    view = CloudRegionViewSet.as_view({"post": "deploy_command"})

    with patch.object(
        RegionService,
        "get_deploy_script",
        return_value="#!/bin/sh\necho ready",
    ) as get_deploy_script:
        response = view(request)

    assert response.status_code == 200
    get_deploy_script.assert_called_once_with({"cloud_region_id": region.id})


@pytest.mark.parametrize(
    ("proxy_address", "normalized"),
    [
        ("10.0.0.8", "10.0.0.8"),
        ("Proxy.Example.COM", "proxy.example.com"),
        ("2001:db8::8", "[2001:db8::8]"),
        ("[2001:db8::8]", "[2001:db8::8]"),
    ],
)
def test_proxy_address_is_normalized_at_the_api_boundary(
    proxy_address,
    normalized,
):
    serializer = CloudRegionProxyAddressSerializer(
        data={"proxy_address": proxy_address}
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["proxy_address"] == normalized
