"""
Tests for verify_otp_code NATS handler rate limiting.

Issue #3440: verify_otp_code had no rate limiting, allowing brute-force
enumeration of any user's OTP within a single 30-second TOTP window.

These tests verify that the fix correctly enforces rate limiting and failure
counting in verify_otp_code, matching the behaviour of verify_otp_login.
"""

import pytest
import pyotp
from django.contrib.auth.hashers import make_password

from apps.system_mgmt.models import User
from apps.system_mgmt.otp_challenge import RATE_LIMIT_MAX_ATTEMPTS, record_failed_attempt


@pytest.fixture
def use_locmem_cache(settings):
    """Use local memory cache for testing instead of dummy cache."""
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-verify-otp-code",
        }
    }


@pytest.fixture
def clear_cache(use_locmem_cache):
    """Clear cache before and after each test."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def otp_user(db):
    """Create a test user with OTP configured."""
    secret = pyotp.random_base32()
    user = User.objects.create(
        username="otp_test_user",
        password=make_password("testpass"),
        display_name="OTP Test User",
        domain="domain.com",
        locale="en",
        timezone="UTC",
        disabled=False,
        otp_secret=secret,
    )
    return user


class TestVerifyOtpCodeRateLimit:
    """Verify that verify_otp_code enforces rate limiting (Issue #3440 fix)."""

    @pytest.mark.django_db
    def test_rate_limit_blocks_after_max_failed_attempts(self, clear_cache, otp_user):
        """
        After RATE_LIMIT_MAX_ATTEMPTS failed OTP guesses from the same IP,
        further calls must return result=False with a rate-limit message.

        This is the core regression test: reverting the fix causes this to fail
        because the old verify_otp_code never calls check_rate_limit.
        """
        from apps.system_mgmt.nats_api import verify_otp_code

        client_ip = "10.0.0.1"
        username = otp_user.username

        # Exhaust the rate limit with wrong OTP codes
        for _ in range(RATE_LIMIT_MAX_ATTEMPTS):
            result = verify_otp_code(username=username, otp_code="000000", client_ip=client_ip)
            # Each attempt before the limit is hit should return invalid OTP
            assert result["result"] is False
            assert "rate" not in result["message"].lower(), (
                f"Hit rate limit too early (attempt {_ + 1})"
            )

        # One more attempt should now be rate-limited
        result = verify_otp_code(username=username, otp_code="000001", client_ip=client_ip)

        assert result["result"] is False
        assert "rate" in result["message"].lower() or "many" in result["message"].lower(), (
            f"Expected rate-limit message, got: {result['message']!r}"
        )

    @pytest.mark.django_db
    def test_correct_otp_succeeds_before_rate_limit(self, clear_cache, otp_user):
        """A correct OTP code should still succeed when under the rate limit."""
        from apps.system_mgmt.nats_api import verify_otp_code

        client_ip = "10.0.0.2"
        totp = pyotp.TOTP(otp_user.otp_secret)
        correct_code = totp.now()

        result = verify_otp_code(
            username=otp_user.username,
            otp_code=correct_code,
            client_ip=client_ip,
        )

        assert result["result"] is True
        assert result["message"] == "Verification successful"

    @pytest.mark.django_db
    def test_correct_otp_resets_rate_limit_counter(self, clear_cache, otp_user):
        """
        A successful OTP verification should reset the failure counter,
        so subsequent failures start from zero again.
        """
        from apps.system_mgmt.nats_api import verify_otp_code

        client_ip = "10.0.0.3"
        username = otp_user.username

        # Record some (but not max) failed attempts
        for _ in range(RATE_LIMIT_MAX_ATTEMPTS - 1):
            verify_otp_code(username=username, otp_code="000000", client_ip=client_ip)

        # A correct OTP clears the counter
        totp = pyotp.TOTP(otp_user.otp_secret)
        correct_code = totp.now()
        result = verify_otp_code(username=username, otp_code=correct_code, client_ip=client_ip)
        assert result["result"] is True

        # After the reset, we should have the full quota again
        # (RATE_LIMIT_MAX_ATTEMPTS more failures before hitting limit)
        for i in range(RATE_LIMIT_MAX_ATTEMPTS):
            result = verify_otp_code(username=username, otp_code="000000", client_ip=client_ip)
            assert result["result"] is False
            assert "rate" not in result["message"].lower(), (
                f"Hit rate limit too early after reset (attempt {i + 1})"
            )

    @pytest.mark.django_db
    def test_rate_limit_checked_before_db_lookup(self, clear_cache, otp_user):
        """
        When already rate-limited, verify_otp_code must return the rate-limit
        response without hitting the database — i.e. the check happens first.
        This also means a non-existent username cannot be used to probe rate state.
        """
        from apps.system_mgmt.nats_api import verify_otp_code

        client_ip = "10.0.0.4"
        username = otp_user.username

        # Pre-fill the rate limit counter directly
        for _ in range(RATE_LIMIT_MAX_ATTEMPTS):
            record_failed_attempt(client_ip, username)

        # Even a correct OTP is blocked at the rate-limit gate
        totp = pyotp.TOTP(otp_user.otp_secret)
        correct_code = totp.now()

        result = verify_otp_code(username=username, otp_code=correct_code, client_ip=client_ip)

        assert result["result"] is False
        assert "rate" in result["message"].lower() or "many" in result["message"].lower()

    @pytest.mark.django_db
    def test_rate_limit_is_per_ip_and_username(self, clear_cache, otp_user):
        """
        Rate limiting must be scoped to (IP, username). A different IP must
        not be blocked by another IP's failures.
        """
        from apps.system_mgmt.nats_api import verify_otp_code

        username = otp_user.username
        blocked_ip = "10.0.0.5"
        clean_ip = "10.0.0.6"

        # Exhaust limit for blocked_ip
        for _ in range(RATE_LIMIT_MAX_ATTEMPTS):
            verify_otp_code(username=username, otp_code="000000", client_ip=blocked_ip)

        blocked_result = verify_otp_code(username=username, otp_code="000000", client_ip=blocked_ip)
        assert blocked_result["result"] is False
        assert "rate" in blocked_result["message"].lower() or "many" in blocked_result["message"].lower()

        # clean_ip must still get an "invalid OTP" response, not a rate-limit
        clean_result = verify_otp_code(username=username, otp_code="000000", client_ip=clean_ip)
        assert clean_result["result"] is False
        assert "rate" not in clean_result["message"].lower()

    @pytest.mark.django_db
    def test_nonexistent_user_returns_not_found(self, clear_cache):
        """verify_otp_code should return user-not-found for unknown usernames."""
        from apps.system_mgmt.nats_api import verify_otp_code

        result = verify_otp_code(
            username="no_such_user_xyz",
            otp_code="123456",
            client_ip="10.0.0.7",
        )

        assert result["result"] is False
        assert "not found" in result["message"].lower()

    @pytest.mark.django_db
    def test_legacy_call_without_client_ip_still_rate_limits(self, clear_cache, otp_user):
        """
        Callers that omit client_ip (backward-compatible default="") must still
        hit rate limiting — the empty string is a valid key prefix and all
        legacy callers share the same "" bucket per username.
        """
        from apps.system_mgmt.nats_api import verify_otp_code

        username = otp_user.username

        # Exhaust with no client_ip (legacy call style)
        for _ in range(RATE_LIMIT_MAX_ATTEMPTS):
            verify_otp_code(username=username, otp_code="000000")

        result = verify_otp_code(username=username, otp_code="000000")
        assert result["result"] is False
        assert "rate" in result["message"].lower() or "many" in result["message"].lower()
