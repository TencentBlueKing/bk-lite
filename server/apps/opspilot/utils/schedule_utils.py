"""
Schedule utilities for Celery beat task configuration.

Provides validation and crontab generation for flexible scheduling:
- daily: Execute at one or more times every day
- weekly: Execute at specified times on specified weekdays
- monthly: Execute at specified times on specified days every month
- crontab: Execute using a custom 5-field crontab expression

Config Format (in workflow_data.nodes[].data.config):
{
    "frequency": "daily"|"weekly"|"monthly"|"crontab",
    "time": ["09:00", "18:00"],        # Required for daily/weekly/monthly (list of HH:MM)
    "weekdays": [1, 3, 5],             # Required for weekly (0=Sunday, 6=Saturday)
    "days": [1, 15],                   # Required for monthly
    "crontab_expression": "30 9 * * 1-5",  # Required for crontab
    "message": "触发消息",
    "params": [],
    "headers": [],
    "inputParams": "last_message",
    "outputParams": "last_message"
}

Legacy Format (still supported, auto-converted):
{
    "frequency": "daily",
    "time": "00:00",          # Single string instead of list
    "message": "xxx"
}
"""

import re
from datetime import datetime
from typing import Any

from croniter import croniter

# Valid frequency types
FREQUENCY_TYPES = ("daily", "weekly", "monthly", "crontab")

# Time format regex (HH:MM, 24-hour)
TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class ScheduleConfigValidator:
    """Validates schedule configurations for Celery beat tasks."""

    @classmethod
    def validate(cls, config: dict[str, Any]) -> None:
        """
        Validate a celery node config.

        Args:
            config: Celery node config dict with keys:
                - frequency: "daily"|"weekly"|"monthly"|"crontab"
                - time: List of HH:MM strings (for daily/weekly/monthly)
                - weekdays: List of ints 0-6 (for weekly, 0=Sunday)
                - days: List of ints 1-31 (for monthly)
                - crontab_expression: str (for crontab)
                - message: str (trigger message)

        Raises:
            ValueError: If configuration is invalid
        """
        if not config:
            raise ValueError("config is required")

        frequency = config.get("frequency")
        if not frequency:
            raise ValueError("frequency is required")

        if frequency not in FREQUENCY_TYPES:
            raise ValueError(f"Invalid frequency: {frequency}. Must be one of: {', '.join(FREQUENCY_TYPES)}")

        if frequency == "crontab":
            cls._validate_crontab(config)
        else:
            cls._validate_time(config)
            if frequency == "weekly":
                cls._validate_weekdays(config)
            elif frequency == "monthly":
                cls._validate_monthly(config)

    @classmethod
    def _validate_time(cls, config: dict[str, Any]) -> None:
        """Validate time field (must be a list of HH:MM strings)."""
        time_value = config.get("time")
        if not time_value:
            raise ValueError("time is required for daily/weekly/monthly schedule")

        if not isinstance(time_value, list):
            raise ValueError("time must be a list")

        if len(time_value) == 0:
            raise ValueError("time must contain at least one time")

        for time_str in time_value:
            if not isinstance(time_str, str):
                raise ValueError(f"Invalid time format: {time_str}. Must be a string.")

            if not TIME_PATTERN.match(time_str):
                raise ValueError(f"Invalid time format: {time_str}. Must be HH:MM (24-hour format)")

    @classmethod
    def _validate_weekdays(cls, config: dict[str, Any]) -> None:
        """Validate weekdays field for weekly schedule."""
        weekdays = config.get("weekdays")
        if not weekdays:
            raise ValueError("weekdays is required for weekly schedule")

        if not isinstance(weekdays, list):
            raise ValueError("weekdays must be a list")

        if len(weekdays) == 0:
            raise ValueError("weekdays must contain at least one weekday")

        for weekday in weekdays:
            if not isinstance(weekday, int):
                raise ValueError(f"Invalid weekday: {weekday}. Must be an integer.")

            if weekday < 0 or weekday > 6:
                raise ValueError(f"Invalid weekday: {weekday}. Must be 0-6 (0=Sunday)")

    @classmethod
    def _validate_monthly(cls, config: dict[str, Any]) -> None:
        """Validate monthly schedule fields."""
        days = config.get("days")
        if not days:
            raise ValueError("days is required for monthly schedule")

        if not isinstance(days, list):
            raise ValueError("days must be a list")

        if len(days) == 0:
            raise ValueError("days must contain at least one day")

        for day in days:
            if not isinstance(day, int):
                raise ValueError(f"Invalid day: {day}. Must be an integer.")

            if day < 1 or day > 31:
                raise ValueError(f"Invalid day: {day}. Must be 1-31")

    @classmethod
    def _validate_crontab(cls, config: dict[str, Any]) -> None:
        """Validate crontab expression."""
        expression = config.get("crontab_expression")
        if not expression:
            raise ValueError("crontab_expression is required for crontab schedule")

        if not isinstance(expression, str):
            raise ValueError("crontab_expression must be a string")

        fields = expression.strip().split()
        if len(fields) != 5:
            raise ValueError(f"Invalid crontab expression: {expression}. Must have exactly 5 fields (minute hour day month weekday)")

        field_names = ["minute", "hour", "day of month", "month", "day of week"]
        field_ranges = [
            (0, 59),  # minute
            (0, 23),  # hour
            (1, 31),  # day of month
            (1, 12),  # month
            (0, 6),  # day of week
        ]

        for i, (field, name, (min_val, max_val)) in enumerate(zip(fields, field_names, field_ranges)):
            cls._validate_crontab_field(field, name, min_val, max_val)

    @classmethod
    def _validate_crontab_field(cls, field: str, name: str, min_val: int, max_val: int) -> None:
        """Validate a single crontab field."""
        if field == "*":
            return

        # Handle step values (e.g., */5, 1-10/2)
        step_parts = field.split("/")
        base = step_parts[0]
        step = step_parts[1] if len(step_parts) > 1 else None

        if step is not None:
            if not step.isdigit() or int(step) < 1:
                raise ValueError(f"Invalid step value in {name} field: {field}")

        if base == "*":
            return

        # Handle lists (e.g., 1,5,10)
        parts = base.split(",")
        for part in parts:
            # Handle ranges (e.g., 1-5)
            if "-" in part:
                range_parts = part.split("-")
                if len(range_parts) != 2:
                    raise ValueError(f"Invalid range in {name} field: {part}")
                start, end = range_parts
                if not start.isdigit() or not end.isdigit():
                    raise ValueError(f"Invalid range in {name} field: {part}")
                start_val, end_val = int(start), int(end)
                if start_val > end_val:
                    raise ValueError(f"Invalid range in {name} field: {part} (start > end)")
                if start_val < min_val or end_val > max_val:
                    raise ValueError(f"Invalid range in {name} field: {part}. Values must be {min_val}-{max_val}")
            else:
                if not part.isdigit():
                    raise ValueError(f"Invalid value in {name} field: {part}")
                val = int(part)
                if val < min_val or val > max_val:
                    raise ValueError(f"Invalid value in {name} field: {part}. Must be {min_val}-{max_val}")


class CrontabGenerator:
    """Generates crontab configurations from schedule configurations."""

    # Mapping from frequency type to generator method
    _GENERATORS: dict[str, str] = {
        "daily": "_generate_daily",
        "weekly": "_generate_weekly",
        "monthly": "_generate_monthly",
        "crontab": "_generate_crontab",
    }

    @classmethod
    def generate(cls, config: dict[str, Any]) -> list[tuple[str, dict[str, str]]]:
        """
        Generate crontab configurations from a celery node config.

        Args:
            config: Validated celery node config

        Returns:
            List of tuples: (task_suffix, crontab_dict)
            where crontab_dict has keys compatible with CrontabSchedule:
            - minute
            - hour
            - day_of_week
            - day_of_month
            - month_of_year
        """
        frequency = config["frequency"]
        generator_name = cls._GENERATORS.get(frequency)

        if generator_name is None:
            raise ValueError(f"Unknown frequency: {frequency}")

        generator = getattr(cls, generator_name)
        return generator(config)

    @classmethod
    def _generate_daily(cls, config: dict[str, Any]) -> list[tuple[str, dict[str, str]]]:
        """Generate crontab for daily schedule."""
        time_list = config["time"]
        result = []

        for index, time_str in enumerate(time_list):
            hour, minute = time_str.split(":")
            crontab_dict = {
                "minute": minute.lstrip("0") or "0",
                "hour": hour.lstrip("0") or "0",
                "day_of_week": "*",
                "day_of_month": "*",
                "month_of_year": "*",
            }
            result.append((str(index), crontab_dict))

        return result

    @classmethod
    def _generate_weekly(cls, config: dict[str, Any]) -> list[tuple[str, dict[str, str]]]:
        """Generate crontab for weekly schedule.

        Combines multiple weekdays into a single crontab entry (e.g., "1,4" for Monday and Thursday).
        """
        time_list = config["time"]
        weekdays = config["weekdays"]

        # Combine weekdays into comma-separated string (e.g., "1,4")
        weekday_str = ",".join(str(d) for d in sorted(weekdays))

        result = []
        for index, time_str in enumerate(time_list):
            hour, minute = time_str.split(":")
            crontab_dict = {
                "minute": minute.lstrip("0") or "0",
                "hour": hour.lstrip("0") or "0",
                "day_of_week": weekday_str,
                "day_of_month": "*",
                "month_of_year": "*",
            }
            result.append((str(index), crontab_dict))

        return result

    @classmethod
    def _generate_monthly(cls, config: dict[str, Any]) -> list[tuple[str, dict[str, str]]]:
        """Generate crontab for monthly schedule (every month on specified days)."""
        time_list = config["time"]
        days = config["days"]

        day_str = ",".join(str(d) for d in sorted(days))

        result = []
        for index, time_str in enumerate(time_list):
            hour, minute = time_str.split(":")
            crontab_dict = {
                "minute": minute.lstrip("0") or "0",
                "hour": hour.lstrip("0") or "0",
                "day_of_week": "*",
                "day_of_month": day_str,
                "month_of_year": "*",
            }
            result.append((str(index), crontab_dict))

        return result

    @classmethod
    def _generate_crontab(cls, config: dict[str, Any]) -> list[tuple[str, dict[str, str]]]:
        """Generate crontab from custom expression."""
        expression = config["crontab_expression"]
        fields = expression.strip().split()

        crontab_dict = {
            "minute": fields[0],
            "hour": fields[1],
            "day_of_month": fields[2],
            "month_of_year": fields[3],
            "day_of_week": fields[4],
        }

        return [("0", crontab_dict)]


def convert_legacy_config(config: dict[str, Any]) -> dict[str, Any]:
    """
    Convert legacy celery node config (single time string) to new format (time list).

    Legacy format:
        {
            "frequency": "daily",
            "time": "00:00",           # Single string
            "message": "xxx",
            ...
        }

    New format:
        {
            "frequency": "daily",
            "time": ["00:00"],         # List of strings
            "message": "xxx",
            ...
        }

    Args:
        config: The celery node config (workflow_data.nodes[].data.config)

    Returns:
        Converted config with time as list, or original if already new format
    """
    # Check if time field exists and is a string (legacy format)
    time_value = config.get("time")

    if time_value is None:
        return config

    # Already new format (time is a list)
    if isinstance(time_value, list):
        return config

    # Legacy format: time is a single string, convert to list
    if isinstance(time_value, str):
        new_config = config.copy()
        new_config["time"] = [time_value]
        return new_config

    return config


def get_crontab_next_runs(
    crontab_expression: str,
    count: int = 6,
    base_time: datetime | None = None,
) -> list[str]:
    """
    Get the next N execution times for a crontab expression.

    Args:
        crontab_expression: 5-field crontab expression (minute hour day month weekday)
        count: Number of next execution times to return (default: 6)
        base_time: Base time to calculate from (default: now)

    Returns:
        List of ISO format datetime strings for next executions

    Raises:
        ValueError: If crontab expression is invalid
    """
    if not crontab_expression or not isinstance(crontab_expression, str):
        raise ValueError("crontab_expression is required and must be a string")

    expression = crontab_expression.strip()

    # Validate format
    if not croniter.is_valid(expression):
        raise ValueError(f"Invalid crontab expression: {expression}")

    if base_time is None:
        base_time = datetime.now()

    try:
        cron = croniter(expression, base_time)
        next_runs = []
        for _ in range(count):
            next_time = cron.get_next(datetime)
            next_runs.append(next_time.strftime("%Y-%m-%d %H:%M:%S"))
        return next_runs
    except Exception as e:
        raise ValueError(f"Failed to calculate next runs: {e}")
