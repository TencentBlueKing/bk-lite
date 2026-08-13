from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from django.core.cache import caches
from django.core.cache.backends.locmem import LocMemCache
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, close_old_connections
from django.utils import timezone

from apps.alerts.models.alert_source import AlertSource
from apps.alerts.service import k8s_install as k8s_install_module
from apps.alerts.service.k8s_install import K8sInstallService
from apps.core.exceptions.base_app_exception import BaseAppException

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def enable_database_token_issuance(settings):
    settings.K8S_INSTALL_TOKEN_DB_ENABLED = True


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


@pytest.mark.parametrize(
    ("usage_count", "max_usage", "constraint_name"),
    [(0, 0, "alerts_k8s_token_max_usage_gt_0"), (2, 1, "alerts_k8s_token_usage_lte_max")],
)
def test_token_check_contracts_are_enforced_by_the_model_layer(usage_count, max_usage, constraint_name):
    from apps.alerts.models.install_token import K8sInstallToken

    with pytest.raises(IntegrityError, match=constraint_name):
        K8sInstallToken.objects.create(
            token_hash=f"invalid-{usage_count}-{max_usage}",
            encrypted_payload="ciphertext",
            usage_count=usage_count,
            max_usage=max_usage,
            expires_at=timezone.now() + timedelta(minutes=1),
        )


def test_disabled_database_issuance_preserves_legacy_shape(token_payload, legacy_cache, settings):
    settings.K8S_INSTALL_TOKEN_DB_ENABLED = False
    token = K8sInstallService.generate_install_token(token_payload)

    cached = legacy_cache.get(K8sInstallService._build_cache_key(token))

    assert cached == {
        **token_payload,
        "usage_count": 0,
        "max_usage": K8sInstallService.TOKEN_MAX_USAGE,
    }
    from apps.alerts.models.install_token import K8sInstallToken

    assert not K8sInstallToken.objects.filter(token_hash=K8sInstallService._hash_token(token)).exists()


def test_mixed_new_workers_can_consume_both_storage_shapes(token_payload, legacy_cache, settings):
    settings.K8S_INSTALL_TOKEN_DB_ENABLED = False
    legacy_token = K8sInstallService.generate_install_token(token_payload)
    settings.K8S_INSTALL_TOKEN_DB_ENABLED = True
    database_token = K8sInstallService.generate_install_token(token_payload)

    assert K8sInstallService.validate_and_get_token_data(legacy_token)["remaining_usage"] == 4
    settings.K8S_INSTALL_TOKEN_DB_ENABLED = False
    assert K8sInstallService.validate_and_get_token_data(database_token)["remaining_usage"] == 4


def test_generation_rejects_empty_encryption_key(token_payload, settings):
    settings.SECRET_KEY = ""
    with pytest.raises((ImproperlyConfigured, ValueError), match="SECRET_KEY"):
        K8sInstallService.generate_install_token(token_payload)


def test_wrong_encryption_key_does_not_consume_usage(token_payload, settings):
    from apps.alerts.models.install_token import K8sInstallToken

    settings.SECRET_KEY = "issuer-key"
    token = K8sInstallService.generate_install_token(token_payload)
    settings.SECRET_KEY = "different-reader-key"

    with pytest.raises(BaseAppException, match="Invalid or expired token"):
        K8sInstallService.validate_and_get_token_data(token)

    record = K8sInstallToken.objects.get(token_hash=K8sInstallService._hash_token(token))
    assert record.usage_count == 0


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


def test_exhausted_legacy_counter_remains_a_tombstone(token_payload, legacy_cache):
    token = "legacy-exhausted-alerts-token"
    cache_key = K8sInstallService._build_cache_key(token)
    usage_cache_key = f"{cache_key}:usage_count"
    legacy_cache.set(
        cache_key,
        {**token_payload, "usage_count": K8sInstallService.TOKEN_MAX_USAGE, "max_usage": K8sInstallService.TOKEN_MAX_USAGE},
        timeout=K8sInstallService.TOKEN_EXPIRE_TIME,
    )

    for _ in range(2):
        with pytest.raises(BaseAppException, match=r"maximum usage limit \(5 times\)"):
            K8sInstallService._consume_legacy_cache_usage(token)

    assert legacy_cache.get(cache_key) is not None
    assert legacy_cache.get(usage_cache_key) > K8sInstallService.TOKEN_MAX_USAGE


def test_missing_and_exhausted_tokens_preserve_existing_errors(token_payload):
    token = K8sInstallService.generate_install_token(token_payload)
    for _ in range(K8sInstallService.TOKEN_MAX_USAGE):
        K8sInstallService.validate_and_get_token_data(token)

    with pytest.raises(BaseAppException, match=r"maximum usage limit \(5 times\)"):
        K8sInstallService.validate_and_get_token_data(token)
    with pytest.raises(BaseAppException, match="Invalid or expired token"):
        K8sInstallService.validate_and_get_token_data("does-not-exist")


def test_render_endpoint_preserves_response_contract(token_payload, api_client):
    AlertSource.objects.create(
        name="K8s",
        source_id="k8s",
        source_type="webhook",
        config={"url": "/api/v1/alerts/api/receiver_data/"},
        team_secrets={"1": "team-secret"},
    )
    token = K8sInstallService.generate_install_token(token_payload)
    response = api_client.post(
        "/api/v1/alerts/open_api/k8s/render/",
        {"token": token},
        format="json",
    )

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/yaml")
    assert response["X-Token-Remaining-Usage"] == "4"
    assert b"team-secret" in response.content


def test_render_endpoint_preserves_error_responses(token_payload, api_client):
    missing = api_client.post("/api/v1/alerts/open_api/k8s/render/", {}, format="json")
    invalid = api_client.post(
        "/api/v1/alerts/open_api/k8s/render/",
        {"token": "does-not-exist"},
        format="json",
    )
    expired_token = K8sInstallService.generate_install_token(token_payload)
    from apps.alerts.models.install_token import K8sInstallToken

    K8sInstallToken.objects.filter(token_hash=K8sInstallService._hash_token(expired_token)).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    expired = api_client.post(
        "/api/v1/alerts/open_api/k8s/render/",
        {"token": expired_token},
        format="json",
    )
    token = K8sInstallService.generate_install_token(token_payload)
    for _ in range(K8sInstallService.TOKEN_MAX_USAGE):
        K8sInstallService.validate_and_get_token_data(token)
    exhausted = api_client.post(
        "/api/v1/alerts/open_api/k8s/render/",
        {"token": token},
        format="json",
    )

    assert (missing.status_code, missing.json()["message"]) == (500, "Missing required parameter: token")
    assert (invalid.status_code, invalid.json()["message"]) == (500, "Invalid or expired token")
    assert (expired.status_code, expired.json()["message"]) == (500, "Invalid or expired token")
    assert (exhausted.status_code, exhausted.json()["message"]) == (500, "Token has exceeded maximum usage limit (5 times)")
