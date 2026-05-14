"""
Tests for OTP Challenge Management Module

Tests cover:
- Challenge creation, verification, and invalidation
- Challenge expiration (one-time use)
- Rate limiting for OTP verification attempts
"""

from unittest.mock import MagicMock, patch

import pytest

from apps.system_mgmt.otp_challenge import (
    CHALLENGE_TTL,
    RATE_LIMIT_MAX_ATTEMPTS,
    check_rate_limit,
    create_challenge,
    invalidate_challenge,
    record_failed_attempt,
    reset_rate_limit,
    verify_challenge,
)


@pytest.fixture
def use_locmem_cache(settings):
    """Use local memory cache for testing instead of dummy cache."""
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "test-otp-challenge",
        }
    }


@pytest.fixture
def clear_cache(use_locmem_cache):
    """Clear cache before each test."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


class TestChallengeCreation:
    """Tests for challenge creation."""

    def test_create_challenge_returns_uuid(self, clear_cache):
        """Challenge ID should be a valid UUID string."""
        challenge_id = create_challenge(user_id=1, username="testuser")

        assert challenge_id is not None
        assert isinstance(challenge_id, str)
        assert len(challenge_id) == 36  # UUID format: 8-4-4-4-12

    def test_create_challenge_stores_data(self, clear_cache):
        """Challenge data should be stored and retrievable."""
        challenge_id = create_challenge(user_id=42, username="alice")

        data = verify_challenge(challenge_id)

        assert data is not None
        assert data["user_id"] == 42
        assert data["username"] == "alice"
        assert "created_at" in data

    def test_create_multiple_challenges_unique(self, clear_cache):
        """Each challenge should have a unique ID."""
        challenge1 = create_challenge(user_id=1, username="user1")
        challenge2 = create_challenge(user_id=1, username="user1")
        challenge3 = create_challenge(user_id=2, username="user2")

        assert challenge1 != challenge2
        assert challenge2 != challenge3
        assert challenge1 != challenge3


class TestChallengeVerification:
    """Tests for challenge verification."""

    def test_verify_valid_challenge(self, clear_cache):
        """Valid challenge should return challenge data."""
        challenge_id = create_challenge(user_id=1, username="testuser")

        data = verify_challenge(challenge_id)

        assert data is not None
        assert data["user_id"] == 1
        assert data["username"] == "testuser"

    def test_verify_invalid_challenge(self, clear_cache):
        """Invalid challenge ID should return None."""
        data = verify_challenge("invalid-challenge-id")

        assert data is None

    def test_verify_empty_challenge(self, clear_cache):
        """Empty challenge ID should return None."""
        assert verify_challenge("") is None
        assert verify_challenge(None) is None

    def test_verify_nonexistent_challenge(self, clear_cache):
        """Non-existent challenge should return None."""
        # Valid UUID format but never created
        data = verify_challenge("12345678-1234-1234-1234-123456789012")

        assert data is None


class TestChallengeInvalidation:
    """Tests for challenge invalidation (one-time use)."""

    def test_invalidate_existing_challenge(self, clear_cache):
        """Invalidating existing challenge should return True."""
        challenge_id = create_challenge(user_id=1, username="testuser")

        result = invalidate_challenge(challenge_id)

        assert result is True

    def test_invalidate_removes_challenge(self, clear_cache):
        """Invalidated challenge should no longer be verifiable."""
        challenge_id = create_challenge(user_id=1, username="testuser")

        invalidate_challenge(challenge_id)
        data = verify_challenge(challenge_id)

        assert data is None

    def test_invalidate_nonexistent_challenge(self, clear_cache):
        """Invalidating non-existent challenge should return False."""
        result = invalidate_challenge("nonexistent-challenge-id")

        assert result is False

    def test_invalidate_empty_challenge(self, clear_cache):
        """Invalidating empty challenge ID should return False."""
        assert invalidate_challenge("") is False
        assert invalidate_challenge(None) is False

    def test_challenge_one_time_use(self, clear_cache):
        """Challenge should only be usable once."""
        challenge_id = create_challenge(user_id=1, username="testuser")

        # First verification should succeed
        data1 = verify_challenge(challenge_id)
        assert data1 is not None

        # Invalidate after use
        invalidate_challenge(challenge_id)

        # Second verification should fail
        data2 = verify_challenge(challenge_id)
        assert data2 is None


class TestRateLimiting:
    """Tests for OTP verification rate limiting."""

    def test_initial_state_not_limited(self, clear_cache):
        """Fresh IP/username should not be rate limited."""
        is_limited, remaining = check_rate_limit("192.168.1.1", "testuser")

        assert is_limited is False
        assert remaining == RATE_LIMIT_MAX_ATTEMPTS

    def test_record_failed_attempt_increments(self, clear_cache):
        """Recording failed attempt should increment counter."""
        ip, username = "192.168.1.1", "testuser"

        attempts1 = record_failed_attempt(ip, username)
        attempts2 = record_failed_attempt(ip, username)
        attempts3 = record_failed_attempt(ip, username)

        assert attempts1 == 1
        assert attempts2 == 2
        assert attempts3 == 3

    def test_rate_limit_after_max_attempts(self, clear_cache):
        """Should be rate limited after max attempts."""
        ip, username = "192.168.1.1", "testuser"

        # Record max attempts
        for _ in range(RATE_LIMIT_MAX_ATTEMPTS):
            record_failed_attempt(ip, username)

        is_limited, remaining = check_rate_limit(ip, username)

        assert is_limited is True
        assert remaining == 0

    def test_rate_limit_remaining_attempts(self, clear_cache):
        """Should correctly report remaining attempts."""
        ip, username = "192.168.1.1", "testuser"

        # Record 2 failed attempts
        record_failed_attempt(ip, username)
        record_failed_attempt(ip, username)

        is_limited, remaining = check_rate_limit(ip, username)

        assert is_limited is False
        assert remaining == RATE_LIMIT_MAX_ATTEMPTS - 2

    def test_rate_limit_per_ip_username_combination(self, clear_cache):
        """Rate limit should be per IP + username combination."""
        # Different users from same IP
        record_failed_attempt("192.168.1.1", "user1")
        record_failed_attempt("192.168.1.1", "user1")

        is_limited1, remaining1 = check_rate_limit("192.168.1.1", "user1")
        is_limited2, remaining2 = check_rate_limit("192.168.1.1", "user2")

        assert is_limited1 is False
        assert remaining1 == RATE_LIMIT_MAX_ATTEMPTS - 2
        assert is_limited2 is False
        assert remaining2 == RATE_LIMIT_MAX_ATTEMPTS  # Different user, fresh counter

    def test_reset_rate_limit(self, clear_cache):
        """Resetting rate limit should clear the counter."""
        ip, username = "192.168.1.1", "testuser"

        # Record some failed attempts
        record_failed_attempt(ip, username)
        record_failed_attempt(ip, username)

        # Reset
        result = reset_rate_limit(ip, username)

        assert result is True

        # Should be back to initial state
        is_limited, remaining = check_rate_limit(ip, username)
        assert is_limited is False
        assert remaining == RATE_LIMIT_MAX_ATTEMPTS

    def test_reset_nonexistent_rate_limit(self, clear_cache):
        """Resetting non-existent rate limit should return False."""
        result = reset_rate_limit("192.168.1.1", "nonexistent")

        assert result is False


class TestChallengeExpiration:
    """Tests for challenge TTL/expiration."""

    def test_challenge_ttl_is_configured(self):
        """Challenge TTL should be 5 minutes (300 seconds)."""
        assert CHALLENGE_TTL == 300

    @patch("apps.system_mgmt.otp_challenge.cache")
    def test_challenge_created_with_ttl(self, mock_cache):
        """Challenge should be created with correct TTL."""
        mock_cache.set = MagicMock()

        create_challenge(user_id=1, username="testuser")

        # Verify cache.set was called with timeout=CHALLENGE_TTL
        mock_cache.set.assert_called_once()
        call_args = mock_cache.set.call_args
        assert call_args[1].get("timeout") == CHALLENGE_TTL or call_args[0][2] == CHALLENGE_TTL
