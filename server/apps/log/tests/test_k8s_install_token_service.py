from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pydantic.root_model  # noqa
import pytest
from django.core.cache import caches
from django.db import close_old_connections
from django.utils import timezone

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.log.models import K8sInstallToken
from apps.log.services.k8s_collect import K8sLogCollectService as K8s

pytestmark = pytest.mark.django_db


@pytest.fixture
def legacy_cache(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "k8s-install-token-compat",
        }
    }
    backend = caches["default"]
    backend.clear()
    yield backend
    backend.clear()


def _legacy_cache_payload(cache_backend, token):
    return cache_backend.get(f"log_k8s_install_token:{token}")


def test_token_lifecycle_increments_usage():
    token = K8s.generate_install_token("cluster-a", "cr-1")
    token_record = K8sInstallToken.objects.get(token_hash=K8s._hash_token(token))
    assert token_record.cluster_name == "cluster-a"

    data = K8s.validate_and_get_token_data(token)

    assert data["cluster_name"] == "cluster-a"
    assert data["cloud_region_id"] == "cr-1"
    assert data["remaining_usage"] == K8s.TOKEN_MAX_USAGE - 1
    token_record.refresh_from_db()
    assert token_record.usage_count == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_validation_never_exceeds_max_usage():
    attempts = K8s.TOKEN_MAX_USAGE * 2
    token = K8s.generate_install_token("cluster-a", "cr-1")

    def consume():
        close_old_connections()
        try:
            return K8s.validate_and_get_token_data(token)["remaining_usage"]
        except BaseAppException:
            return None
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=attempts) as executor:
        remaining_usage = list(executor.map(lambda _: consume(), range(attempts)))

    assert sorted(value for value in remaining_usage if value is not None) == list(range(K8s.TOKEN_MAX_USAGE))
    token_record = K8sInstallToken.objects.get(token_hash=K8s._hash_token(token))
    assert token_record.usage_count == K8s.TOKEN_MAX_USAGE


def test_validation_does_not_extend_token_ttl():
    token = K8s.generate_install_token("cluster-a", "cr-1")
    token_record = K8sInstallToken.objects.get(token_hash=K8s._hash_token(token))
    expires_at = token_record.expires_at

    K8s.validate_and_get_token_data(token)

    token_record.refresh_from_db()
    assert token_record.expires_at == expires_at


def test_validation_fails_closed_when_authoritative_record_is_missing(legacy_cache):
    token = K8s.generate_install_token("cluster-a", "cr-1")
    K8sInstallToken.objects.filter(token_hash=K8s._hash_token(token)).delete()
    legacy_key = f"log_k8s_install_token:{token}"
    payload = {"cluster_name": "cluster-a"}
    legacy_cache.set(legacy_key, payload, timeout=K8s.TOKEN_EXPIRE_TIME)

    assert _legacy_cache_payload(legacy_cache, token) == payload
    with pytest.raises(BaseAppException, match="Invalid or expired token"):
        K8s.validate_and_get_token_data(token)


def test_legacy_cache_only_token_fails_closed(legacy_cache):
    token = "legacy-cache-only"
    legacy_key = f"log_k8s_install_token:{token}"
    payload = {
        "cluster_name": "cluster-a",
        "cloud_region_id": "cr-1",
        "config_type": "log",
        "usage_count": 0,
        "max_usage": K8s.TOKEN_MAX_USAGE,
    }
    legacy_cache.set(
        legacy_key,
        payload,
        timeout=K8s.TOKEN_EXPIRE_TIME,
    )

    assert _legacy_cache_payload(legacy_cache, token) == payload
    with pytest.raises(BaseAppException, match="Invalid or expired token"):
        K8s.validate_and_get_token_data(token)


def test_new_token_is_not_consumable_by_legacy_cache_path(legacy_cache):
    token = K8s.generate_install_token("cluster-a", "cr-1")

    assert _legacy_cache_payload(legacy_cache, token) is None
    assert K8s.validate_and_get_token_data(token)["remaining_usage"] == 4


def test_validate_token_missing_raises():
    with pytest.raises(BaseAppException, match="Token is required"):
        K8s.validate_and_get_token_data("")


def test_validate_token_not_found_raises():
    with pytest.raises(BaseAppException, match="Invalid or expired token"):
        K8s.validate_and_get_token_data("nope")


def test_validate_token_expired_deletes_and_raises():
    token = K8s.generate_install_token("cluster-a", "cr-1")
    K8sInstallToken.objects.filter(token_hash=K8s._hash_token(token)).update(expires_at=timezone.now() - timedelta(seconds=1))

    with pytest.raises(BaseAppException, match="Invalid or expired token"):
        K8s.validate_and_get_token_data(token)
    assert not K8sInstallToken.objects.filter(token_hash=K8s._hash_token(token)).exists()


def test_validate_token_exceeds_max_usage_keeps_tombstone():
    token = K8s.generate_install_token("cluster-a", "cr-1")
    for _ in range(K8s.TOKEN_MAX_USAGE):
        K8s.validate_and_get_token_data(token)

    with pytest.raises(BaseAppException, match="maximum usage limit"):
        K8s.validate_and_get_token_data(token)

    token_record = K8sInstallToken.objects.get(token_hash=K8s._hash_token(token))
    assert token_record.usage_count == K8s.TOKEN_MAX_USAGE
