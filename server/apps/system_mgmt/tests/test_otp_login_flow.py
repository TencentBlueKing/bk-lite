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

from apps.system_mgmt.models import Role, SystemSettings, User
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
        assert result["data"]["need_binding"] is True
        assert "need_bindng" not in result["data"]
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


class TestOtpLoginWithTemporaryPassword:
    """Tests for OTP login flow with temporary_pwd flag (Issue #2981)."""

    @pytest.fixture
    def temporary_pwd_user(self, db):
        """Create a user with temporary password flag set."""
        user = User.objects.create(
            username="temppwduser",
            password=make_password("temppass123"),
            display_name="Temp Password User",
            domain="domain.com",
            locale="en",
            timezone="UTC",
            disabled=False,
            temporary_pwd=True,
            otp_secret="JBSWY3DPEHPK3PXP",  # OTP configured
        )
        return user

    @pytest.mark.django_db
    def test_otp_first_phase_includes_temporary_pwd_true(self, clear_cache, temporary_pwd_user, enable_otp_setting):
        """OTP first phase response should include temporary_pwd=True for temp password users."""
        from apps.system_mgmt.nats_api import get_user_login_token

        result = get_user_login_token(user=temporary_pwd_user, username=temporary_pwd_user.username, skip_token_for_otp=True)

        assert result["result"] is True
        assert "challenge_id" in result["data"]
        assert result["data"]["require_otp"] is True
        # Critical: temporary_pwd must be included in first phase response
        assert "temporary_pwd" in result["data"]
        assert result["data"]["temporary_pwd"] is True

    @pytest.mark.django_db
    def test_otp_first_phase_includes_temporary_pwd_false(self, clear_cache, otp_enabled_user, enable_otp_setting):
        """OTP first phase response should include temporary_pwd=False for normal users."""
        from apps.system_mgmt.nats_api import get_user_login_token

        # Ensure user has temporary_pwd=False
        otp_enabled_user.temporary_pwd = False
        otp_enabled_user.save()

        result = get_user_login_token(user=otp_enabled_user, username=otp_enabled_user.username, skip_token_for_otp=True)

        assert result["result"] is True
        assert "challenge_id" in result["data"]
        assert result["data"]["require_otp"] is True
        # temporary_pwd should be included and be False
        assert "temporary_pwd" in result["data"]
        assert result["data"]["temporary_pwd"] is False

    @pytest.mark.django_db
    def test_verify_otp_returns_temporary_pwd_true(self, clear_cache, temporary_pwd_user, enable_otp_setting):
        """OTP verification response should include temporary_pwd=True for temp password users."""
        import pyotp

        from apps.system_mgmt.nats_api import verify_otp_login

        challenge_id = create_challenge(user_id=temporary_pwd_user.id, username=temporary_pwd_user.username)

        totp = pyotp.TOTP(temporary_pwd_user.otp_secret)
        valid_code = totp.now()

        with patch.dict(os.environ, {"SECRET_KEY": "test-secret-key"}):
            result = verify_otp_login(challenge_id=challenge_id, otp_code=valid_code, client_ip="127.0.0.1")

        assert result["result"] is True
        assert "token" in result["data"]
        # Critical: temporary_pwd must be included in OTP verification response
        assert "temporary_pwd" in result["data"]
        assert result["data"]["temporary_pwd"] is True

    @pytest.mark.django_db
    def test_verify_otp_returns_temporary_pwd_false(self, clear_cache, otp_enabled_user, enable_otp_setting):
        """OTP verification response should include temporary_pwd=False for normal users."""
        import pyotp

        from apps.system_mgmt.nats_api import verify_otp_login

        # Ensure user has temporary_pwd=False
        otp_enabled_user.temporary_pwd = False
        otp_enabled_user.save()

        challenge_id = create_challenge(user_id=otp_enabled_user.id, username=otp_enabled_user.username)

        totp = pyotp.TOTP(otp_enabled_user.otp_secret)
        valid_code = totp.now()

        with patch.dict(os.environ, {"SECRET_KEY": "test-secret-key"}):
            result = verify_otp_login(challenge_id=challenge_id, otp_code=valid_code, client_ip="127.0.0.1")

        assert result["result"] is True
        assert "token" in result["data"]
        # temporary_pwd should be included and be False
        assert "temporary_pwd" in result["data"]
        assert result["data"]["temporary_pwd"] is False


@pytest.fixture
def expiring_soon_user(clear_cache):
    """Create a user with password expiring in 5 days (175 days old with 180-day validity)."""
    from datetime import timedelta

    import pyotp
    from django.utils import timezone

    user = User.objects.create(
        username="expiringsoonuser",
        domain="domain.com",
        password=make_password("testpassword"),
        otp_secret=pyotp.random_base32(),
        password_last_modified=timezone.now() - timedelta(days=175),  # 180-175=5 days left
    )
    yield user
    user.delete()


class TestPasswordExpiryBlocksLogin:
    """Test that expired passwords block login before OTP verification."""

    @pytest.fixture
    def expired_password_user(self, clear_cache):
        """Create a user with an expired password (181 days old to exceed 180-day validity)."""
        from datetime import timedelta

        import pyotp
        from django.utils import timezone

        user = User.objects.create(
            username="expireduser",
            password=make_password("testpassword"),
            domain="domain.com",
            otp_secret=pyotp.random_base32(),
            password_last_modified=timezone.now() - timedelta(days=181),
        )
        yield user
        user.delete()

    @pytest.mark.django_db
    def test_expired_password_blocks_login_without_otp(self, clear_cache, expired_password_user):
        """Login should be blocked for expired password users (no OTP)."""
        from apps.system_mgmt.nats_api import login

        result = login(username="expireduser", password="testpassword")

        assert result["result"] is False
        # Check for expiry-related keywords in English or Chinese
        msg = result["message"].lower()
        assert "expired" in msg or "contact" in msg or "过期" in msg or "管理员" in msg

    @pytest.mark.django_db
    def test_expired_password_blocks_login_before_otp(self, clear_cache, expired_password_user, enable_otp_setting):
        """Login should be blocked for expired password users BEFORE OTP verification."""
        from apps.system_mgmt.nats_api import login

        result = login(username="expireduser", password="testpassword")

        # Should be blocked immediately, not proceed to OTP
        assert result["result"] is False
        # Check for expiry-related keywords in English or Chinese
        msg = result["message"].lower()
        assert "expired" in msg or "contact" in msg or "过期" in msg or "管理员" in msg
        # Should NOT have challenge_id (OTP phase should not be reached)
        assert "challenge_id" not in result.get("data", {})

    @pytest.mark.django_db
    def test_expiring_soon_password_allows_login_with_reminder(self, clear_cache, expiring_soon_user):
        """Login should succeed for expiring-soon password with reminder."""
        from apps.system_mgmt.nats_api import login

        with patch.dict(os.environ, {"SECRET_KEY": "test-secret-key"}):
            result = login(username="expiringsoonuser", password="testpassword")

        assert result["result"] is True
        assert "password_expiry_reminder" in result["data"]
        assert result["data"]["password_expiry_reminder"] != ""


class TestAdminExpiredPasswordForcedReset:
    """Tests for admin expired-password behavior entering forced reset flow."""

    @pytest.fixture
    def expired_admin_user(self, clear_cache):
        """Create the special admin account with an expired password."""
        from datetime import timedelta

        from django.utils import timezone

        admin_role, _ = Role.objects.get_or_create(name="admin", app="")
        user = User.objects.create(
            username="admin",
            password=make_password("adminpassword"),
            display_name="Admin",
            domain="domain.com",
            locale="en",
            timezone="UTC",
            disabled=False,
            role_list=[admin_role.id],
            password_last_modified=timezone.now() - timedelta(days=181),
        )
        yield user
        user.delete()

    @pytest.fixture
    def expired_other_superuser(self, clear_cache):
        """Create another global admin-role user that should NOT use the admin-only override."""
        from datetime import timedelta

        from django.utils import timezone

        admin_role, _ = Role.objects.get_or_create(name="admin", app="")
        user = User.objects.create(
            username="root-admin",
            password=make_password("rootpassword"),
            display_name="Root Admin",
            domain="domain.com",
            locale="en",
            timezone="UTC",
            disabled=False,
            role_list=[admin_role.id],
            password_last_modified=timezone.now() - timedelta(days=181),
        )
        yield user
        user.delete()

    @pytest.mark.django_db
    def test_expired_admin_password_enters_forced_reset_without_otp(self, clear_cache, expired_admin_user):
        """Expired account named admin should enter forced reset flow instead of hard-failing login."""
        from apps.system_mgmt.nats_api import login

        with patch.dict(os.environ, {"SECRET_KEY": "test-secret-key"}):
            result = login(username="admin", password="adminpassword")

        assert result["result"] is True
        assert result["data"]["temporary_pwd"] is True
        assert "token" in result["data"]

    @pytest.mark.django_db
    def test_expired_admin_password_with_otp_preserves_otp_first_flow(self, clear_cache, expired_admin_user, enable_otp_setting):
        """Expired account named admin with OTP enabled should still go through OTP first."""
        import pyotp

        from apps.system_mgmt.nats_api import login, verify_otp_login

        result = login(username="admin", password="adminpassword")

        assert result["result"] is True
        assert result["data"].get("require_otp") is True
        assert "challenge_id" in result["data"]
        assert result["data"]["temporary_pwd"] is True

        expired_admin_user.refresh_from_db()
        valid_code = pyotp.TOTP(expired_admin_user.otp_secret).now()

        with patch.dict(os.environ, {"SECRET_KEY": "test-secret-key"}):
            otp_result = verify_otp_login(
                challenge_id=result["data"]["challenge_id"],
                otp_code=valid_code,
                client_ip="127.0.0.1",
            )

        assert otp_result["result"] is True
        assert otp_result["data"]["temporary_pwd"] is True

    @pytest.mark.django_db
    def test_expired_other_superuser_still_hard_fails(self, clear_cache, expired_other_superuser):
        """Expired superusers whose username is not admin should keep the old hard-fail behavior."""
        from apps.system_mgmt.nats_api import login

        result = login(username="root-admin", password="rootpassword")

        assert result["result"] is False
        msg = result["message"].lower()
        assert "expired" in msg or "contact" in msg or "过期" in msg or "管理员" in msg
        assert "challenge_id" not in result.get("data", {})

    @pytest.mark.django_db
    def test_expiring_soon_password_with_otp_shows_reminder_after_verification(self, clear_cache, expiring_soon_user, enable_otp_setting):
        """OTP verification should include password expiry reminder for expiring-soon users."""
        import pyotp

        from apps.system_mgmt.nats_api import login, verify_otp_login

        # First phase: should proceed to OTP
        result = login(username="expiringsoonuser", password="testpassword")
        assert result["result"] is True
        assert result["data"].get("require_otp") is True
        challenge_id = result["data"]["challenge_id"]

        # Second phase: OTP verification should include reminder
        totp = pyotp.TOTP(expiring_soon_user.otp_secret)
        valid_code = totp.now()

        with patch.dict(os.environ, {"SECRET_KEY": "test-secret-key"}):
            result = verify_otp_login(challenge_id=challenge_id, otp_code=valid_code, client_ip="127.0.0.1")

        assert result["result"] is True
        assert "password_expiry_reminder" in result["data"]
        assert result["data"]["password_expiry_reminder"] != ""
