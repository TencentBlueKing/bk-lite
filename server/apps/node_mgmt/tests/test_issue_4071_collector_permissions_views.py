import pytest
from django.core.cache import cache, caches

from apps.node_mgmt.models import Collector


pytestmark = pytest.mark.django_db
BASE = "/api/v1/node_mgmt/api/collector"


@pytest.fixture
def collector_cache(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "issue-4071-collector-permissions",
        }
    }
    caches.close_all()
    yield cache
    cache.clear()
    caches.close_all()


def _collector_payload(collector_id: str) -> dict:
    return {
        "id": collector_id,
        "name": "Issue 4071 Collector",
        "service_type": "svc",
        "node_operating_system": "linux",
        "cpu_architecture": "x86_64",
        "executable_path": "/opt/collector/bin/collector",
        "execute_parameters": "--config %s",
    }


def _grant_permissions(user, *permissions):
    user.permission = {"node": set(permissions)}


def test_collector_create_requires_add_permission(api_client, authenticated_user, collector_cache):
    payload = _collector_payload("issue-4071-create")

    denied = api_client.post(f"{BASE}/", payload, format="json")

    assert denied.status_code == 403
    assert not Collector.objects.filter(id=payload["id"]).exists()

    _grant_permissions(authenticated_user, "collector_list-Add")
    collector_cache.set("collectors_etag", "stale")
    allowed = api_client.post(f"{BASE}/", payload, format="json")

    assert allowed.status_code == 201
    assert collector_cache.get("collectors_etag") is None
    assert Collector.objects.filter(id=payload["id"], is_pre=False).exists()


def test_collector_partial_update_requires_edit_permission(api_client, authenticated_user, collector_cache):
    collector = Collector.objects.create(**_collector_payload("issue-4071-update"), is_pre=True)

    denied = api_client.patch(f"{BASE}/{collector.id}/", {"executable_path": "/tmp/denied"}, format="json")

    assert denied.status_code == 403
    collector.refresh_from_db()
    assert collector.executable_path == "/opt/collector/bin/collector"

    _grant_permissions(authenticated_user, "collector_list-Edit")
    collector_cache.set("collectors_etag", "stale")
    allowed = api_client.patch(
        f"{BASE}/{collector.id}/",
        {"executable_path": "/opt/collector/bin/updated"},
        format="json",
    )

    assert allowed.status_code == 200
    assert collector_cache.get("collectors_etag") is None
    collector.refresh_from_db()
    assert collector.executable_path == "/opt/collector/bin/updated"


def test_collector_full_update_requires_edit_permission(api_client, authenticated_user):
    collector = Collector.objects.create(**_collector_payload("issue-4071-put"), is_pre=False)
    payload = _collector_payload(collector.id)
    payload["executable_path"] = "/opt/collector/bin/replaced"

    denied = api_client.put(f"{BASE}/{collector.id}/", payload, format="json")

    assert denied.status_code == 403
    collector.refresh_from_db()
    assert collector.executable_path == "/opt/collector/bin/collector"

    _grant_permissions(authenticated_user, "collector_list-Edit")
    allowed = api_client.put(f"{BASE}/{collector.id}/", payload, format="json")

    assert allowed.status_code == 200
    collector.refresh_from_db()
    assert collector.executable_path == "/opt/collector/bin/replaced"


def test_collector_destroy_requires_delete_permission(api_client, authenticated_user, collector_cache):
    collector = Collector.objects.create(**_collector_payload("issue-4071-delete"), is_pre=True)

    denied = api_client.delete(f"{BASE}/{collector.id}/")

    assert denied.status_code == 403
    assert Collector.objects.filter(id=collector.id).exists()

    _grant_permissions(authenticated_user, "collector_list-Delete")
    collector_cache.set("collectors_etag", "stale")
    allowed = api_client.delete(f"{BASE}/{collector.id}/")

    assert allowed.status_code == 200
    assert collector_cache.get("collectors_etag") is None
    assert not Collector.objects.filter(id=collector.id).exists()
