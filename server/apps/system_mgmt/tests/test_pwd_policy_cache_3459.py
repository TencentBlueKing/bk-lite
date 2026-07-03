"""
Tests for Issue #3459: SystemSettings batch-read + cache in login handler.

Verifies that:
1. _get_pwd_policy_settings() issues exactly ONE DB query for all keys,
   not separate per-key queries.
2. Subsequent calls within TTL hit cache (zero additional DB queries).
3. invalidate_pwd_policy_cache() clears cache so next call re-queries DB.
4. login() with wrong password calls _get_pwd_policy_settings() once per
   request, not once per key (i.e., reverting the fix should break the test).
5. update_sys_set viewset action invalidates cache when pwd_set_* keys change.
"""

import pytest
from django.core.cache import cache
from unittest.mock import patch, call

from apps.system_mgmt.utils.pwd_policy_cache import (
    get_pwd_policy_settings,
    invalidate_pwd_policy_cache,
    PWD_POLICY_CACHE_KEY,
    PWD_POLICY_DEFAULTS,
    PWD_POLICY_KEYS,
)


@pytest.fixture(autouse=True)
def use_locmem_cache(settings):
    """Override DummyCache (from conftest) with LocMemCache so we can actually test caching."""
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
def test_get_pwd_policy_settings_returns_defaults_when_no_rows():
    """With no SystemSettings rows, helper returns built-in defaults."""
    result = get_pwd_policy_settings()
    assert result == PWD_POLICY_DEFAULTS


@pytest.mark.django_db
def test_get_pwd_policy_settings_single_batch_query():
    """Helper must issue exactly one DB query (batch filter) not N single-key queries."""
    from apps.system_mgmt.models.system_settings import SystemSettings

    SystemSettings.objects.update_or_create(key="pwd_set_max_retry_count", defaults={"value": "3"})
    SystemSettings.objects.update_or_create(key="pwd_set_lock_duration", defaults={"value": "60"})

    # Count DB queries — must be exactly 1 (batch filter), not 2+ (per-key filters)
    with patch.object(
        SystemSettings.objects.__class__,
        "filter",
        wraps=SystemSettings.objects.filter,
    ) as mock_filter:
        result = get_pwd_policy_settings()

    assert result["pwd_set_max_retry_count"] == 3
    assert result["pwd_set_lock_duration"] == 60
    # Defaults for keys not in DB
    assert result["pwd_set_validity_period"] == PWD_POLICY_DEFAULTS["pwd_set_validity_period"]
    assert result["pwd_set_expiry_reminder_days"] == PWD_POLICY_DEFAULTS["pwd_set_expiry_reminder_days"]

    # filter() should have been called exactly once, with key__in= (batch), not per-key
    assert mock_filter.call_count == 1
    call_kwargs = mock_filter.call_args[1]
    assert "key__in" in call_kwargs, "Expected key__in= batch query, got per-key queries"
    assert set(call_kwargs["key__in"]) == set(PWD_POLICY_KEYS)


@pytest.mark.django_db
def test_get_pwd_policy_settings_caches_result():
    """Second call within TTL must not hit DB (cache hit)."""
    from apps.system_mgmt.models.system_settings import SystemSettings

    SystemSettings.objects.update_or_create(key="pwd_set_max_retry_count", defaults={"value": "7"})

    # First call populates cache
    result1 = get_pwd_policy_settings()
    assert result1["pwd_set_max_retry_count"] == 7

    # Mutate DB — cache should shield the second call
    SystemSettings.objects.filter(key="pwd_set_max_retry_count").update(value="99")

    result2 = get_pwd_policy_settings()
    assert result2["pwd_set_max_retry_count"] == 7, (
        "Second call should return cached value, not the DB-mutated value"
    )


@pytest.mark.django_db
def test_invalidate_pwd_policy_cache_clears_cache():
    """After invalidation, next call must re-query DB and pick up new value."""
    from apps.system_mgmt.models.system_settings import SystemSettings

    SystemSettings.objects.update_or_create(key="pwd_set_max_retry_count", defaults={"value": "5"})

    # Prime cache
    result1 = get_pwd_policy_settings()
    assert result1["pwd_set_max_retry_count"] == 5

    # Simulate admin updating the setting
    SystemSettings.objects.filter(key="pwd_set_max_retry_count").update(value="10")

    # Before invalidation: still stale
    assert get_pwd_policy_settings()["pwd_set_max_retry_count"] == 5

    # Invalidate
    invalidate_pwd_policy_cache()
    assert cache.get(PWD_POLICY_CACHE_KEY) is None

    # After invalidation: fresh DB value
    result2 = get_pwd_policy_settings()
    assert result2["pwd_set_max_retry_count"] == 10


@pytest.mark.django_db
def test_login_wrong_password_calls_get_pwd_policy_once(django_user_model):
    """login() with wrong password must call _get_pwd_policy_settings() exactly once,
    not once per SystemSettings key (revert the fix and this test fails)."""
    from django.contrib.auth.hashers import make_password
    from apps.system_mgmt.models import User
    from apps.system_mgmt.models.system_settings import SystemSettings

    # Setup: user with a known password
    user = User.objects.create(
        username="test_3459",
        domain="domain.com",
        password=make_password("correct_password"),
        password_error_count=0,
    )

    SystemSettings.objects.update_or_create(key="pwd_set_max_retry_count", defaults={"value": "5"})
    SystemSettings.objects.update_or_create(key="pwd_set_lock_duration", defaults={"value": "180"})

    call_count = []

    original_fn = get_pwd_policy_settings.__wrapped__ if hasattr(get_pwd_policy_settings, "__wrapped__") else None

    with patch(
        "apps.system_mgmt.nats_api._get_pwd_policy_settings",
        wraps=get_pwd_policy_settings,
    ) as mock_policy:
        from apps.system_mgmt.nats_api import login

        result = login("test_3459", "wrong_password")

    assert result["result"] is False
    # Must have been called exactly once — one batched call, not one per key
    assert mock_policy.call_count == 1, (
        f"Expected _get_pwd_policy_settings called once, got {mock_policy.call_count} calls. "
        "This suggests the fix was reverted to per-key queries."
    )


@pytest.mark.django_db
def test_update_sys_set_invalidates_pwd_policy_cache(client):
    """update_sys_set viewset action must call invalidate_pwd_policy_cache() when pwd_set_* keys are updated."""
    from django.test import RequestFactory
    from apps.system_mgmt.viewset.system_settings_viewset import SystemSettingsViewSet
    from apps.system_mgmt.utils.pwd_policy_cache import invalidate_pwd_policy_cache

    # Prime the cache
    cache.set(PWD_POLICY_CACHE_KEY, {"pwd_set_max_retry_count": 5}, 300)
    assert cache.get(PWD_POLICY_CACHE_KEY) is not None

    with patch("apps.system_mgmt.viewset.system_settings_viewset._invalidate_pwd_policy_cache") as mock_inv:
        with patch("apps.system_mgmt.viewset.system_settings_viewset.log_operation"):
            factory = RequestFactory()
            request = factory.post("/", data={"pwd_set_max_retry_count": "8"}, content_type="application/json")
            # 鉴权桩：update_sys_set 受 @HasPermission("security_settings-Edit") 保护，
            # 超管可绕过权限校验，确保进入缓存失效分支
            import types as _types
            request.user = _types.SimpleNamespace(
                username="pwd-policy-admin",
                domain="domain.com",
                is_superuser=True,
                is_authenticated=True,
                permission={"system_mgmt": {"security_settings-Edit"}},
            )
            request.data = {"pwd_set_max_retry_count": "8"}

            view = SystemSettingsViewSet()
            view.request = request
            view.kwargs = {}
            view.format_kwarg = None
            view.update_sys_set(request)

    mock_inv.assert_called_once()
