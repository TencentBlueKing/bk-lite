import json
import re

HABIT_KEY_PATTERN = re.compile(r"^[a-zA-Z0-9._-]{1,100}$")
MAX_HABIT_VALUE_BYTES = 16 * 1024
COLUMN_PREFERENCE_KEY_PREFIX = "view.columnPreference."
ALERT_CHART_HABIT_KEY = "event.alert.chartExpanded"
SEARCH_HISTOGRAM_HABIT_KEY = "search.histogramExpanded"


class InvalidHabitKey(ValueError):
    pass


class InvalidHabitValue(ValueError):
    pass


def validate_habit_key(habit_key: str) -> str:
    if not isinstance(habit_key, str) or not HABIT_KEY_PATTERN.fullmatch(habit_key):
        raise InvalidHabitKey("习惯键格式无效")
    return habit_key


def validate_habit_value(habit_value) -> dict:
    if not isinstance(habit_value, dict) or isinstance(habit_value, list):
        raise InvalidHabitValue("习惯值必须是对象")
    encoded = json.dumps(habit_value, ensure_ascii=False).encode("utf-8")
    if len(encoded) > MAX_HABIT_VALUE_BYTES:
        raise InvalidHabitValue("习惯值过大")
    return habit_value


def column_preference_habit_key(object_id) -> str:
    return f"{COLUMN_PREFERENCE_KEY_PREFIX}{object_id}"
