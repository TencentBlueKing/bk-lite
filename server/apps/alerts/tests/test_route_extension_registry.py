from django.http import JsonResponse
from django.urls import path
import pytest

from apps.alerts.extensions.routes import alert_extension_routes


@pytest.fixture(autouse=True)
def preserve_alert_extension_routes():
    original_entries = {
        key: list(patterns)
        for key, patterns in alert_extension_routes._entries.items()
    }
    try:
        yield
    finally:
        alert_extension_routes.clear()
        for key, patterns in original_entries.items():
            alert_extension_routes.register(key, patterns)


def _example_view(_request):
    return JsonResponse({"result": True})


def test_alert_route_extension_is_empty_for_community_edition():
    alert_extension_routes.clear()

    assert alert_extension_routes.urlpatterns == []


def test_alert_route_extension_registers_idempotently_and_preserves_list_identity():
    alert_extension_routes.clear()
    shared_patterns = alert_extension_routes.urlpatterns
    first = [path("api/enterprise/example/", _example_view, name="enterprise-example")]
    replacement = [path("api/enterprise/replaced/", _example_view, name="enterprise-replaced")]

    alert_extension_routes.register("enterprise-example", first)
    alert_extension_routes.register("enterprise-example", replacement)

    assert alert_extension_routes.urlpatterns is shared_patterns
    assert [pattern.name for pattern in shared_patterns] == ["enterprise-replaced"]
