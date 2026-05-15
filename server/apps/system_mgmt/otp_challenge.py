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

# Rate limiting configuration
RATE_LIMIT_TTL = 300  # 5 minutes
RATE_LIMIT_MAX_ATTEMPTS = 5
RATE_LIMIT_PREFIX = "otp_rate_limit:"


def create_challenge(user_id: int, username: str) -> str:
    """
    Create a new OTP challenge for a user.

    Args:
        user_id: The user's database ID
        username: The user's username

    Returns:
        A unique challenge_id (UUID string)
    """
    challenge_id = str(uuid.uuid4())
    cache_key = f"{CHALLENGE_PREFIX}{challenge_id}"

    challenge_data = {
        "user_id": user_id,
        "username": username,
        "created_at": datetime.now().isoformat(),
    }

    cache.set(cache_key, challenge_data, timeout=CHALLENGE_TTL)
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
    return cache.delete(cache_key)


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
