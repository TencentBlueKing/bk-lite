from apps.core.user_habit import (
    InvalidHabitKey,
    InvalidHabitValue,
    column_preference_habit_key,
    validate_habit_key,
    validate_habit_value,
)
import pytest


def test_validate_habit_key_accepts_dotted_keys():
    assert validate_habit_key("event.alert.chartExpanded") == "event.alert.chartExpanded"


@pytest.mark.parametrize("habit_key", ["", "bad key", "slash/key", "a" * 101])
def test_validate_habit_key_rejects_invalid_values(habit_key):
    with pytest.raises(InvalidHabitKey):
        validate_habit_key(habit_key)


def test_validate_habit_value_rejects_non_objects():
    with pytest.raises(InvalidHabitValue):
        validate_habit_value(["expanded"])


def test_column_preference_habit_key_is_stable():
    assert column_preference_habit_key(12) == "view.columnPreference.12"
