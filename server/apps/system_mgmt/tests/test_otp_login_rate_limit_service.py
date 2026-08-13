from concurrent.futures import ThreadPoolExecutor
from time import sleep

import pytest
from django.core.cache import cache

from apps.system_mgmt.otp_challenge import RATE_LIMIT_MAX_ATTEMPTS, check_otp_login_account_rate_limit, reserve_otp_login_account_attempt


@pytest.fixture
def locmem_cache(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "otp-account-limit-pure",
        }
    }
    cache.clear()
    yield
    cache.clear()


def test_account_limit_reserves_concurrent_attempts_atomically(locmem_cache):
    with ThreadPoolExecutor(max_workers=RATE_LIMIT_MAX_ATTEMPTS) as executor:
        attempts = list(executor.map(reserve_otp_login_account_attempt, [42] * RATE_LIMIT_MAX_ATTEMPTS))

    assert sorted(attempts) == list(range(1, RATE_LIMIT_MAX_ATTEMPTS + 1))
    assert check_otp_login_account_rate_limit(42) == (True, 0)


def test_account_limit_expiry_rolls_from_latest_attempt(locmem_cache, monkeypatch):
    monkeypatch.setattr("apps.system_mgmt.otp_challenge.RATE_LIMIT_TTL", 1)
    for _ in range(RATE_LIMIT_MAX_ATTEMPTS):
        reserve_otp_login_account_attempt(42)

    sleep(0.6)
    reserve_otp_login_account_attempt(42)
    sleep(0.6)

    assert check_otp_login_account_rate_limit(42) == (True, 0)
