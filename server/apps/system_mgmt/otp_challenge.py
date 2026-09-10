"""
OTP Challenge Management Module

Provides secure challenge-based OTP verification for two-factor authentication.
Challenges are stored in Django Cache (Redis) with automatic expiration.
"""

import uuid
from datetime import datetime

from django.core.cache import cache

# Challenge configuration
CHALLENGE_TTL = 300  # 5 minutes
CHALLENGE_PREFIX = "otp_challenge:"
ACTIVE_CHALLENGE_PREFIX = "otp_active_challenge:"

# Rate limiting configuration
RATE_LIMIT_TTL = 300  # 5 minutes
RATE_LIMIT_MAX_ATTEMPTS = 5
RATE_LIMIT_PREFIX = "otp_rate_limit:"
OTP_LOGIN_ACCOUNT_RATE_LIMIT_PREFIX = "otp_login_account_rate_limit:"


def create_challenge(user_id: int, username: str, pending_otp_secret: str | None = None) -> str:
    """
    Create a new OTP challenge for a user.

    Args:
        user_id: The user's database ID
        username: The user's username
        pending_otp_secret: Unbound TOTP secret for first-time binding. Stored only
            on this challenge until verification succeeds; not persisted on the user.

    Returns:
        A unique challenge_id (UUID string)
    """
    previous_challenge_id = cache.get(f"{ACTIVE_CHALLENGE_PREFIX}{user_id}")
    if previous_challenge_id:
        invalidate_challenge(previous_challenge_id)

    challenge_id = str(uuid.uuid4())
    cache_key = f"{CHALLENGE_PREFIX}{challenge_id}"

    challenge_data = {
        "user_id": user_id,
        "username": username,
        "created_at": datetime.now().isoformat(),
    }
    if pending_otp_secret:
        challenge_data["pending_otp_secret"] = pending_otp_secret

    cache.set(cache_key, challenge_data, timeout=CHALLENGE_TTL)
    cache.set(f"{ACTIVE_CHALLENGE_PREFIX}{user_id}", challenge_id, timeout=CHALLENGE_TTL)
    return challenge_id


def verify_challenge(challenge_id: str) -> dict | None:
    """
    Verify and retrieve challenge data.

    Args:
        challenge_id: The challenge ID to verify

    Returns:
        Challenge data dict if valid, None if invalid/expired
    """
    if not challenge_id:
        return None

    cache_key = f"{CHALLENGE_PREFIX}{challenge_id}"
    challenge_data = cache.get(cache_key)

    return challenge_data


def invalidate_challenge(challenge_id: str) -> bool:
    """
    Invalidate a challenge after successful use (one-time use).

    Args:
        challenge_id: The challenge ID to invalidate

    Returns:
        True if challenge was deleted, False if it didn't exist
    """
    if not challenge_id:
        return False

    cache_key = f"{CHALLENGE_PREFIX}{challenge_id}"
    challenge_data = cache.get(cache_key)
    deleted = cache.delete(cache_key)
    if challenge_data:
        user_id = challenge_data.get("user_id")
        active_key = f"{ACTIVE_CHALLENGE_PREFIX}{user_id}"
        if cache.get(active_key) == challenge_id:
            cache.delete(active_key)
    return deleted


def check_rate_limit(ip: str, username: str) -> tuple[bool, int]:
    """
    Check if OTP verification is rate limited.

    Args:
        ip: Client IP address
        username: Username being verified

    Returns:
        Tuple of (is_limited, remaining_attempts)
        - is_limited: True if rate limit exceeded
        - remaining_attempts: Number of attempts remaining (0 if limited)
    """
    cache_key = f"{RATE_LIMIT_PREFIX}{ip}:{username}"
    attempts = cache.get(cache_key, 0)

    if attempts >= RATE_LIMIT_MAX_ATTEMPTS:
        return True, 0

    return False, RATE_LIMIT_MAX_ATTEMPTS - attempts


def record_failed_attempt(ip: str, username: str) -> int:
    """
    Record a failed OTP verification attempt.

    Args:
        ip: Client IP address
        username: Username being verified

    Returns:
        Current number of failed attempts
    """
    cache_key = f"{RATE_LIMIT_PREFIX}{ip}:{username}"
    attempts = cache.get(cache_key, 0)
    attempts += 1
    cache.set(cache_key, attempts, timeout=RATE_LIMIT_TTL)
    return attempts


def reset_rate_limit(ip: str, username: str) -> bool:
    """
    Reset rate limit counter after successful verification.

    Args:
        ip: Client IP address
        username: Username being verified

    Returns:
        True if counter was reset, False if it didn't exist
    """
    cache_key = f"{RATE_LIMIT_PREFIX}{ip}:{username}"
    return cache.delete(cache_key)


def check_otp_login_account_rate_limit(user_id: int) -> tuple[bool, int]:
    """Check the forwarding-header-independent OTP login limit."""
    attempts = cache.get(f"{OTP_LOGIN_ACCOUNT_RATE_LIMIT_PREFIX}{user_id}", 0)
    if attempts >= RATE_LIMIT_MAX_ATTEMPTS:
        return True, 0
    return False, RATE_LIMIT_MAX_ATTEMPTS - attempts


def reserve_otp_login_account_attempt(user_id: int) -> int:
    """Atomically reserve one OTP verification attempt for an account."""
    cache_key = f"{OTP_LOGIN_ACCOUNT_RATE_LIMIT_PREFIX}{user_id}"
    if cache.add(cache_key, 1, timeout=RATE_LIMIT_TTL):
        return 1
    try:
        attempts = cache.incr(cache_key)
        cache.touch(cache_key, timeout=RATE_LIMIT_TTL)
        return attempts
    except ValueError:
        # The key can expire between add() and incr(); retry bounded initialization.
        cache.add(cache_key, 1, timeout=RATE_LIMIT_TTL)
        return cache.get(cache_key, 1)


def reset_otp_login_account_rate_limit(user_id: int) -> bool:
    """Clear the account-scoped OTP login counter after successful verification."""
    return cache.delete(f"{OTP_LOGIN_ACCOUNT_RATE_LIMIT_PREFIX}{user_id}")
