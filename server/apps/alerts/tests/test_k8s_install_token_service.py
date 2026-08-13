from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from django.core.cache import caches
from django.core.cache.backends.locmem import LocMemCache
from django.db import close_old_connections
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from apps.alerts.models.alert_source import AlertSource
from apps.alerts.service import k8s_install as k8s_install_module
from apps.alerts.service.k8s_install import K8sInstallService
from apps.alerts.views.open_api_k8s import K8sOpenAPIViewSet
from apps.core.exceptions.base_app_exception import BaseAppException

pytestmark = pytest.mark.django_db


@pytest.fixture
def token_payload():
    return {
        "server_url": "https://host:8000",
        "cluster_name": "prod",
        "push_source_id": "k8s-prod",
        "source_id": "k8s",
        "receiver_url": "https://host:8000/api/v1/alerts/api/receiver_data/",
        "secret": "team-secret",
        "insecure_skip_verify": False,
    }


@pytest.fixture
def legacy_cache(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "alerts-k8s-token-compat",
        }
    }
    backend = caches["default"]
    backend.clear()
    yield backend
    backend.clear()


def test_token_is_shared_across_worker_local_caches(monkeypatch, token_payload):
    worker_a = LocMemCache("alerts-token-worker-a", {})
    worker_b = LocMemCache("alerts-token-worker-b", {})
    monkeypatch.setattr(k8s_install_module, "cache", worker_a)
    token = K8sInstallService.generate_install_token(token_payload)

    monkeypatch.setattr(k8s_install_module, "cache", worker_b)
    data = K8sInstallService.validate_and_get_token_data(token)

    assert data["cluster_name"] == "prod"
    assert data["secret"] == "team-secret"
    assert data["remaining_usage"] == K8sInstallService.TOKEN_MAX_USAGE - 1


def test_token_payload_is_encrypted_at_rest(token_payload):
    from apps.alerts.models.install_token import K8sInstallToken

    token = K8sInstallService.generate_install_token(token_payload)
    record = K8sInstallToken.objects.get(token_hash=K8sInstallService._hash_token(token))

    assert token not in record.encrypted_payload
    assert token_payload["secret"] not in record.encrypted_payload
    assert record.usage_count == 0
    assert record.max_usage == K8sInstallService.TOKEN_MAX_USAGE


@pytest.mark.django_db(transaction=True)
def test_concurrent_validation_never_exceeds_max_usage(token_payload):
    from apps.alerts.models.install_token import K8sInstallToken

    attempts = K8sInstallService.TOKEN_MAX_USAGE * 2
    token = K8sInstallService.generate_install_token(token_payload)

    def consume():
        close_old_connections()
        try:
            return K8sInstallService.validate_and_get_token_data(token)["remaining_usage"]
        except BaseAppException:
            return None
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=attempts) as executor:
        remaining_usage = list(executor.map(lambda _: consume(), range(attempts)))

    assert sorted(value for value in remaining_usage if value is not None) == list(range(K8sInstallService.TOKEN_MAX_USAGE))
    record = K8sInstallToken.objects.get(token_hash=K8sInstallService._hash_token(token))
    assert record.usage_count == K8sInstallService.TOKEN_MAX_USAGE


def test_validation_does_not_extend_token_expiry(token_payload):
    from apps.alerts.models.install_token import K8sInstallToken

    token = K8sInstallService.generate_install_token(token_payload)
    record = K8sInstallToken.objects.get(token_hash=K8sInstallService._hash_token(token))
    expires_at = record.expires_at

    K8sInstallService.validate_and_get_token_data(token)

    record.refresh_from_db()
    assert record.expires_at == expires_at


def test_expired_token_is_deleted_and_rejected(token_payload):
    from apps.alerts.models.install_token import K8sInstallToken

    token = K8sInstallService.generate_install_token(token_payload)
    token_hash = K8sInstallService._hash_token(token)
    K8sInstallToken.objects.filter(token_hash=token_hash).update(expires_at=timezone.now() - timedelta(seconds=1))

    with pytest.raises(BaseAppException, match="Invalid or expired token"):
        K8sInstallService.validate_and_get_token_data(token)

    assert not K8sInstallToken.objects.filter(token_hash=token_hash).exists()


def test_legacy_cache_token_remains_usable_during_compatibility_window(token_payload, legacy_cache):
    token = "legacy-alerts-token"
    cache_key = K8sInstallService._build_cache_key(token)
    legacy_cache.set(
        cache_key,
        {**token_payload, "usage_count": 2, "max_usage": K8sInstallService.TOKEN_MAX_USAGE},
        timeout=K8sInstallService.TOKEN_EXPIRE_TIME,
    )
    assert legacy_cache.get(cache_key)["usage_count"] == 2
    expires_at = legacy_cache._expire_info[legacy_cache.make_and_validate_key(cache_key)]

    data = K8sInstallService.validate_and_get_token_data(token)

    assert data["secret"] == "team-secret"
    assert data["remaining_usage"] == 2
    assert legacy_cache._expire_info[legacy_cache.make_and_validate_key(cache_key)] == expires_at


def test_legacy_cache_token_uses_an_atomic_compatibility_counter(token_payload, legacy_cache):
    token = "legacy-concurrent-alerts-token"
    legacy_cache.set(
        K8sInstallService._build_cache_key(token),
        {**token_payload, "usage_count": 0, "max_usage": K8sInstallService.TOKEN_MAX_USAGE},
        timeout=K8sInstallService.TOKEN_EXPIRE_TIME,
    )

    def consume():
        try:
            result = K8sInstallService._consume_legacy_cache_usage(token)
            if not result:
                return None
            _, usage_count, max_usage = result
            return max_usage - usage_count
        except BaseAppException:
            return None

    with ThreadPoolExecutor(max_workers=K8sInstallService.TOKEN_MAX_USAGE * 2) as executor:
        remaining_usage = list(executor.map(lambda _: consume(), range(K8sInstallService.TOKEN_MAX_USAGE * 2)))

    assert sorted(value for value in remaining_usage if value is not None) == list(range(K8sInstallService.TOKEN_MAX_USAGE))


def test_missing_and_exhausted_tokens_preserve_existing_errors(token_payload):
    token = K8sInstallService.generate_install_token(token_payload)
    for _ in range(K8sInstallService.TOKEN_MAX_USAGE):
        K8sInstallService.validate_and_get_token_data(token)

    with pytest.raises(BaseAppException, match=r"maximum usage limit \(5 times\)"):
        K8sInstallService.validate_and_get_token_data(token)
    with pytest.raises(BaseAppException, match="Invalid or expired token"):
        K8sInstallService.validate_and_get_token_data("does-not-exist")


def test_render_endpoint_preserves_response_contract(token_payload):
    AlertSource.objects.create(
        name="K8s",
        source_id="k8s",
        source_type="webhook",
        config={"url": "/api/v1/alerts/api/receiver_data/"},
        team_secrets={"1": "team-secret"},
    )
    token = K8sInstallService.generate_install_token(token_payload)
    request = APIRequestFactory().post(
        "/api/v1/alerts/open_api/k8s/render/",
        {"token": token},
        format="json",
    )

    response = K8sOpenAPIViewSet.as_view({"post": "render"})(request)

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/yaml")
    assert response["X-Token-Remaining-Usage"] == "4"
    assert b"team-secret" in response.content
