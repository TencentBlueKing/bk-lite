import pytest
from rest_framework.test import APIRequestFactory, force_authenticate


pytestmark = pytest.mark.django_db


def test_k3s_onboarding_routes_are_registered_independently():
    from apps.monitor.urls import router

    prefixes = {prefix for prefix, _viewset, _basename in router.registry}
    assert "api/k3s_onboarding" in prefixes
    assert "open_api/k3s_onboarding" in prefixes
    assert "open_api/infra" in prefixes


def test_create_instance_view_checks_scope_and_calls_k3s_module(mocker):
    from apps.monitor.views.k3s_onboarding import K3SOnboardingViewSet

    factory = APIRequestFactory()
    request = factory.post(
        "/api/k3s_onboarding/create_instance/",
        {
            "monitor_object_id": 9,
            "instance_id": "edge-1",
            "name": "边缘 K3S",
            "organizations": [10],
        },
        format="json",
    )
    force_authenticate(
        request,
        user=mocker.Mock(is_authenticated=True),
    )
    mocker.patch(
        "apps.monitor.views.k3s_onboarding._build_actor_context",
        return_value={"actor": "test"},
    )
    ensure_orgs = mocker.patch(
        "apps.monitor.views.k3s_onboarding._ensure_target_organizations"
    )
    create = mocker.patch(
        "apps.monitor.views.k3s_onboarding.K3SOnboardingService.create_instance",
        return_value={"instance_id": "('edge-1',)"},
    )

    response = K3SOnboardingViewSet.as_view(
        {"post": "create_instance"}
    )(request)

    assert response.status_code == 200
    ensure_orgs.assert_called_once_with([10], {"actor": "test"})
    create.assert_called_once_with(
        monitor_object_id=9,
        instance_id="edge-1",
        name="边缘 K3S",
        organizations=[10],
    )


def test_open_render_returns_yaml_and_remaining_usage(mocker):
    from apps.monitor.views.k3s_onboarding import K3SOnboardingOpenViewSet

    factory = APIRequestFactory()
    request = factory.post(
        "/open_api/k3s_onboarding/render/",
        {"token": "token-1"},
        format="json",
    )
    render = mocker.patch(
        "apps.monitor.views.k3s_onboarding.K3SOnboardingService.render_manifest",
        return_value={"yaml": "kind: Namespace", "remaining_usage": 4},
    )

    response = K3SOnboardingOpenViewSet.as_view({"post": "render"})(request)

    assert response.status_code == 200
    assert response.content == b"kind: Namespace"
    assert response["Content-Type"].startswith("text/yaml")
    assert response["X-Token-Remaining-Usage"] == "4"
    render.assert_called_once_with("token-1")
