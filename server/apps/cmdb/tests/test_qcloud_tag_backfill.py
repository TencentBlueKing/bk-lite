"""腾讯云历史字符串 tag 回填。"""

import pytest

from apps.cmdb.validators.field_validator import backfill_tag_property

pytestmark = pytest.mark.unit


def test_backfill_tag_property_converts_csv_and_leaves_existing_lists():
    assert backfill_tag_property(None) == (None, 0, 0)
    assert backfill_tag_property(["env:prod"]) == (None, 0, 0)
    assert backfill_tag_property("env:prod,team:net") == (["env:prod", "team:net"], 0, 0)
    assert backfill_tag_property("") == ([], 0, 0)

    values, skipped, truncated = backfill_tag_property("env:prod,bad value,team:net")
    assert values == ["env:prod", "team:net"]
    assert skipped == 1
    assert truncated == 0
    assert backfill_tag_property(123) == ([], 1, 0)

    many = ",".join(f"k{i}:v{i}" for i in range(21))
    values, skipped, truncated = backfill_tag_property(many)
    assert values == [f"k{i}:v{i}" for i in range(20)]
    assert skipped == 0
    assert truncated == 1
