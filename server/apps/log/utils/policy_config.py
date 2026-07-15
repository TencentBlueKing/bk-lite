"""Validation helpers shared by log policy API and scan tasks."""


TIMING_VALUE_LIMITS = {
    "min": 59,
    "hour": 23,
    "day": 1,
}


def validate_timing_config(config, field_name):
    """Return a timing config that is safe for cron and scan-window math."""
    if not isinstance(config, dict):
        raise ValueError(f"{field_name} must be an object")

    timing_type = config.get("type")
    if timing_type not in TIMING_VALUE_LIMITS:
        allowed_types = ", ".join(TIMING_VALUE_LIMITS)
        raise ValueError(f"{field_name}.type must be one of: {allowed_types}")

    value = config.get("value")
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field_name}.value must be a positive integer")

    max_value = TIMING_VALUE_LIMITS[timing_type]
    if not 1 <= value <= max_value:
        raise ValueError(f"{field_name}.value must be between 1 and {max_value} for type {timing_type}")

    return config
