"""
Tests for OTP Login Flow

Tests cover:
- Login with OTP enabled returns challenge_id instead of token
- Login with OTP disabled returns token normally
- verify_otp_login endpoint validates OTP and issues token
- Rate limiting integration in verify_otp_login
"""

import os
from unittest.mock import patch

import pytest
from django.contrib.auth.hashers import make_password

from apps.system_mgmt.models import SystemSettings, User
from apps.system_mgmt.otp_challenge import RATE_LIMIT_MAX_ATTEMPTS, create_challenge


@pytest.fixture
def use_locmem_cache(settings):
    """Use local memory cache for testing."""
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-otp-login",
        }
    }


@pytest.fixture
def clear_cache(use_locmem_cache):
    """Clear cache before each test."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def test_user(db):
    """Create a test user."""
    user = User.objects.create(
        username="testuser",
        password=make_password("testpass123"),
        display_name="Test User",
        domain="domain.com",
        locale="en",
        timezone="UTC",
        disabled=False,
    )
    return user


@pytest.fixture
def otp_enabled_user(test_user):
    """User with OTP configured."""
    test_user.otp_secret = "JBSWY3DPEHPK3PXP"  # Test secret
    test_user.save()
    return test_user


@pytest.fixture
def enable_otp_setting(db):
    """Enable OTP globally."""
    setting, _ = SystemSettings.objects.get_or_create(key="enable_otp", defaults={"value": "1"})
    setting.value = "1"
    setting.save()
    return setting


@pytest.fixture
def disable_otp_setting(db):
    """Disable OTP globally."""
    SystemSettings.objects.filter(key="enable_otp").delete()


class TestLoginFlowWithOTP:
    """Tests for login flow when OTP is enabled."""

    @pytest.mark.django_db
    def test_login_with_otp_configured_returns_challenge_id(self, clear_cache, otp_enabled_user, enable_otp_setting):
        """When OTP is enabled and user has OTP configured, login should return challenge_id."""
        from apps.system_mgmt.nats_api import get_user_login_token

        result = get_user_login_token(user=otp_enabled_user, username=otp_enabled_user.username, skip_token_for_otp=True)

        assert result["result"] is True
        assert "challenge_id" in result["data"]
        assert result["data"]["require_otp"] is True
        assert "token" not in result["data"]
        assert "qr_code" not in result["data"]  # No QR code for already configured users
        assert result["data"]["username"] == otp_enabled_user.username

    @pytest.mark.django_db
    def test_login_with_otp_not_configured_returns_challenge_and_qrcode(self, clear_cache, test_user, enable_otp_setting):
        """When OTP is enabled but user hasn't configured OTP, return challenge_id with QR code."""
        from apps.system_mgmt.nats_api import get_user_login_token

        # User has no otp_secret
        assert test_user.otp_secret is None or test_user.otp_secret == ""

        result = get_user_login_token(user=test_user, username=test_user.username, skip_token_for_otp=True)

        assert result["result"] is True
        assert "challenge_id" in result["data"]
        assert result["data"]["require_otp"] is True
        assert "token" not in result["data"]
        # QR code should be included for first-time binding
        assert "qr_code" in result["data"]
        assert result["data"]["need_bindng"] is True
        # User should now have otp_secret set
        test_user.refresh_from_db()
        assert test_user.otp_secret is not None and test_user.otp_secret != ""

    @pytest.mark.django_db
    def test_login_without_otp_returns_token(self, clear_cache, test_user, disable_otp_setting):
        """When OTP is disabled, login should return token normally."""
        from apps.system_mgmt.nats_api import get_user_login_token

        with patch.dict(os.environ, {"SECRET_KEY": "test-secret-key"}):
            result = get_user_login_token(user=test_user, username=test_user.username, skip_token_for_otp=True)

        assert result["result"] is True
        assert "token" in result["data"]
        assert "challenge_id" not in result["data"]
        assert result["data"].get("require_otp") is not True

    @pytest.mark.django_db
    def test_login_disabled_user_rejected(self, clear_cache, test_user):
        """Disabled user should be rejected."""
        from apps.system_mgmt.nats_api import get_user_login_token

        test_user.disabled = True
        test_user.save()

        result = get_user_login_token(user=test_user, username=test_user.username, skip_token_for_otp=True)

        assert result["result"] is False
        assert "disabled" in result["message"].lower()


class TestVerifyOtpLogin:
    """Tests for verify_otp_login endpoint."""

    @pytest.mark.django_db
    def test_verify_otp_with_valid_challenge_and_code(self, clear_cache, otp_enabled_user, enable_otp_setting):
        """Valid challenge and OTP code should issue token."""
        import pyotp

        from apps.system_mgmt.nats_api import verify_otp_login

        # Create a challenge
        challenge_id = create_challenge(user_id=otp_enabled_user.id, username=otp_enabled_user.username)

        # Generate valid OTP code
        totp = pyotp.TOTP(otp_enabled_user.otp_secret)
        valid_code = totp.now()

        with patch.dict(os.environ, {"SECRET_KEY": "test-secret-key"}):
            result = verify_otp_login(challenge_id=challenge_id, otp_code=valid_code, client_ip="127.0.0.1")

        assert result["result"] is True
        assert "token" in result["data"]
        assert result["data"]["username"] == otp_enabled_user.username

    @pytest.mark.django_db
    def test_verify_otp_with_invalid_code(self, clear_cache, otp_enabled_user, enable_otp_setting):
        """Invalid OTP code should be rejected."""
        from apps.system_mgmt.nats_api import verify_otp_login

        challenge_id = create_challenge(user_id=otp_enabled_user.id, username=otp_enabled_user.username)

        result = verify_otp_login(challenge_id=challenge_id, otp_code="000000", client_ip="127.0.0.1")  # Invalid code

        assert result["result"] is False
        assert "token" not in result.get("data", {})

    @pytest.mark.django_db
    def test_verify_otp_with_invalid_challenge(self, clear_cache):
        """Invalid challenge should be rejected."""
        from apps.system_mgmt.nats_api import verify_otp_login

        result = verify_otp_login(challenge_id="invalid-challenge-id", otp_code="123456", client_ip="127.0.0.1")

        assert result["result"] is False

    @pytest.mark.django_db
    def test_verify_otp_challenge_one_time_use(self, clear_cache, otp_enabled_user, enable_otp_setting):
        """Challenge should only be usable once."""
        import pyotp

        from apps.system_mgmt.nats_api import verify_otp_login

        challenge_id = create_challenge(user_id=otp_enabled_user.id, username=otp_enabled_user.username)

        totp = pyotp.TOTP(otp_enabled_user.otp_secret)
        valid_code = totp.now()

        with patch.dict(os.environ, {"SECRET_KEY": "test-secret-key"}):
            # First verification should succeed
            result1 = verify_otp_login(challenge_id=challenge_id, otp_code=valid_code, client_ip="127.0.0.1")
            assert result1["result"] is True

            # Second verification should fail (challenge invalidated)
            result2 = verify_otp_login(challenge_id=challenge_id, otp_code=valid_code, client_ip="127.0.0.1")
            assert result2["result"] is False

    @pytest.mark.django_db
    def test_verify_otp_rate_limiting(self, clear_cache, otp_enabled_user, enable_otp_setting):
        """Should be rate limited after max failed attempts."""
        from apps.system_mgmt.nats_api import verify_otp_login
        from apps.system_mgmt.otp_challenge import record_failed_attempt

        challenge_id = create_challenge(user_id=otp_enabled_user.id, username=otp_enabled_user.username)

        # Simulate max failed attempts
        for _ in range(RATE_LIMIT_MAX_ATTEMPTS):
            record_failed_attempt("127.0.0.1", otp_enabled_user.username)

        # Next attempt should be rate limited
        result = verify_otp_login(challenge_id=challenge_id, otp_code="123456", client_ip="127.0.0.1")

        assert result["result"] is False
        assert "rate" in result["message"].lower() or "limit" in result["message"].lower() or "attempts" in result["message"].lower()
