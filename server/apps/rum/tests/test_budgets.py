from apps.rum.constants import DEFAULT_BUDGETS, MAX_BUDGETS
from apps.rum.services.validation import valid_budgets


def test_default_budgets_fit_under_the_caps():
    assert DEFAULT_BUDGETS == {
        "requestsPerMinute": 6_000,
        "compressedBytesPerMinute": 32 << 20,
        "decompressedBytesPerMinute": 128 << 20,
        "eventsPerMinute": 20_000,
    }
    assert valid_budgets(DEFAULT_BUDGETS)
    assert valid_budgets(dict(MAX_BUDGETS))


def test_budgets_reject_values_above_the_cap():
    budgets = dict(DEFAULT_BUDGETS)
    budgets["requestsPerMinute"] = MAX_BUDGETS["requestsPerMinute"] + 1
    assert valid_budgets(budgets) is False


def test_budgets_reject_decompressed_below_compressed():
    budgets = dict(DEFAULT_BUDGETS)
    budgets["decompressedBytesPerMinute"] = budgets["compressedBytesPerMinute"] - 1
    assert valid_budgets(budgets) is False


def test_budgets_reject_bool_and_missing_keys():
    assert valid_budgets({"requestsPerMinute": True}) is False
    assert valid_budgets({}) is False
