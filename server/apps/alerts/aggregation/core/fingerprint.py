import hashlib
from typing import Dict, List


def generate_fingerprint(dimensions: Dict[str, str]) -> str:
    """
    Generate MD5 fingerprint from dimension key-value pairs.

    Args:
        dimensions: Dictionary of dimension names and their values

    Returns:
        32-character MD5 hash string

    Example:
        >>> generate_fingerprint({"service": "api", "location": "us-west"})
        'a1b2c3d4e5f6...'
    """
    if not dimensions:
        return hashlib.md5(b"").hexdigest()

    sorted_pairs = sorted(dimensions.items())
    fingerprint_str = "|".join(f"{key}:{value}" for key, value in sorted_pairs)

    return hashlib.md5(fingerprint_str.encode("utf-8")).hexdigest()


def validate_dimensions(dimensions: Dict[str, str]) -> bool:
    """
    Validate that dimensions dictionary contains valid data.

    Args:
        dimensions: Dictionary to validate

    Returns:
        True if valid, False otherwise
    """
    if not isinstance(dimensions, dict):
        return False

    for key, value in dimensions.items():
        if not isinstance(key, str) or not isinstance(value, str):
            return False
        if not key or not value:
            return False

    return True
