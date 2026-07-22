"""告警中心工具函数覆盖测试：util / rule_matcher / time_range_checker。

对照 specs/capabilities/legacy-prd-告警中心-配置.md：分派/屏蔽规则的匹配与生效时间范围判断。
"""

import datetime

import pytest
from django.utils import timezone

from apps.alerts.utils import util
from apps.alerts.utils.rule_matcher import RuleMatcher, filter_by_rules
from apps.alerts.utils.time_range_checker import TimeRangeChecker, check_time_range

# --------------------------------------------------------------------------
# util.py 纯函数
# --------------------------------------------------------------------------


def test_gen_app_secret_length():
    assert len(util.gen_app_secret()) == 32


def test_split_list():
    assert util.split_list([1, 2, 3, 4, 5], count=2) == [[1, 2], [3, 4], [5]]
    assert util.split_list([], count=2) == []


def test_parse_time_to_seconds():
    assert util._parse_time_to_seconds("5min") == 300
    assert util._parse_time_to_seconds("2h") == 7200
    assert util._parse_time_to_seconds("30s") == 30
    assert util._parse_time_to_seconds("3") == 180


def test_parse_time_to_minutes():
    assert util._parse_time_to_minutes("5min") == 5
    assert util._parse_time_to_minutes("2h") == 120
    assert util._parse_time_to_minutes("7") == 7


def test_window_size_to_int():
    assert util.window_size_to_int("5min") == 5
    assert util.window_size_to_int("1h") == 60
    assert util.window_size_to_int("90s") == 1
    assert util.window_size_to_int("180s") == 3
    with pytest.raises(ValueError):
        util.window_size_to_int("bad")


def test_str_to_md5():
    assert util.str_to_md5("abc") == "900150983cd24fb0d6963f7d28e17f72"


def test_generate_instance_fingerprint_consistent():
    data = {"item": "cpu", "resource_id": "1", "resource_type": "host", "alert_source": "prometheus"}
    fp1 = util.generate_instance_fingerprint(data)
    fp2 = util.generate_instance_fingerprint(data)
    assert fp1 == fp2
    assert len(fp1) == 32


def test_generate_instance_fingerprint_empty_fields_use_unknown():
    fp_empty = util.generate_instance_fingerprint({})
    fp_unknown = util.generate_instance_fingerprint(
        {"item": "unknown", "resource_id": "unknown", "resource_type": "unknown", "alert_source": "unknown"}
    )
    assert fp_empty == fp_unknown


def test_generate_instance_fingerprint_custom_fields():
    fp = util.generate_instance_fingerprint({"a": "1", "b": "2"}, fields=["a", "b"])
    assert len(fp) == 32


def test_catch_exception_swallows_and_returns_none():
    @util.catch_exception
    def boom():
        raise RuntimeError("x")

    assert boom() is None

    @util.catch_exception
    def ok():
        return 42

    assert ok() == 42


def test_build_team_secret_payload_is_stable_json():
    payload = util.build_team_secret_payload("sec", 7)
    assert '"source_secret": "sec"' in payload
    assert '"team_id": "7"' in payload


def test_encode_decode_team_secret_roundtrip():
    token = util.encode_team_secret("my-secret", "5")
    decoded = util.decode_team_secret(token)
    assert decoded == {"source_secret": "my-secret", "team_id": "5"}


def test_decode_team_secret_invalid_inputs():
    assert util.decode_team_secret("") is None
    assert util.decode_team_secret("not-a-valid-token") is None


def test_image_to_base64_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        util.image_to_base64("/nonexistent/path/x.png")


# --------------------------------------------------------------------------
# parse_aggregation_window_size
# --------------------------------------------------------------------------


def test_parse_aggregation_window_size_default_on_none():
    assert util.parse_aggregation_window_size(None) == (10, None)


def test_parse_aggregation_window_size_valid():
    assert util.parse_aggregation_window_size(30) == (30, None)


def test_parse_aggregation_window_size_invalid_raises():
    with pytest.raises(ValueError):
        util.parse_aggregation_window_size(0)
    with pytest.raises(ValueError):
        util.parse_aggregation_window_size(True)


def test_parse_aggregation_window_size_clamp_invalid():
    value, note = util.parse_aggregation_window_size(-5, clamp=True)
    assert value == 10
    assert note.startswith("invalid:")


def test_parse_aggregation_window_size_clamp_too_large():
    value, note = util.parse_aggregation_window_size(99999, clamp=True)
    assert value == 1440
    assert note.startswith("clamped:")


def test_parse_aggregation_window_size_too_large_raises():
    with pytest.raises(ValueError):
        util.parse_aggregation_window_size(99999)


# --------------------------------------------------------------------------
# RuleMatcher
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_rule_matcher_eq():
    from apps.alerts.models.models import Level

    Level.objects.create(level_id=0, level_name="Critical", level_display_name="严重", level_type="alert")
    Level.objects.create(level_id=1, level_name="Warning", level_display_name="警告", level_type="alert")

    mapping = {"name": "level_name"}
    rules = [[{"key": "name", "operator": "eq", "value": "Critical"}]]
    ids = filter_by_rules(Level.objects.all(), rules, mapping)
    assert len(ids) == 1


@pytest.mark.django_db
def test_rule_matcher_eq_list_matches_any_selected_value():
    from apps.alerts.models.models import Level

    critical = Level.objects.create(level_id=0, level_name="Critical", level_display_name="致命", level_type="alert")
    error = Level.objects.create(level_id=1, level_name="Error", level_display_name="错误", level_type="alert")
    warning = Level.objects.create(level_id=2, level_name="Warning", level_display_name="预警", level_type="alert")
    matcher = RuleMatcher({"level": "level_id"})

    ids = matcher.filter_queryset(
        Level.objects.all(),
        [[{"key": "level", "operator": "eq", "value": ["0", "1"]}]],
    )

    assert set(ids) == {critical.id, error.id}
    assert warning.id not in ids


@pytest.mark.django_db
def test_rule_matcher_ne_list_excludes_every_selected_value():
    from apps.alerts.models.models import Level

    critical = Level.objects.create(level_id=0, level_name="Critical", level_display_name="致命", level_type="alert")
    error = Level.objects.create(level_id=1, level_name="Error", level_display_name="错误", level_type="alert")
    warning = Level.objects.create(level_id=2, level_name="Warning", level_display_name="预警", level_type="alert")
    matcher = RuleMatcher({"level": "level_id"})

    ids = matcher.filter_queryset(
        Level.objects.all(),
        [[{"key": "level", "operator": "ne", "value": ["0", "1"]}]],
    )

    assert ids == [warning.id]
    assert critical.id not in ids
    assert error.id not in ids


def test_rule_matcher_empty_list_is_invalid():
    matcher = RuleMatcher({"level": "level"})
    assert matcher.build_single_rule_q({"key": "level", "operator": "eq", "value": []}) is None
    assert matcher.build_single_rule_q({"key": "level", "operator": "ne", "value": []}) is None


@pytest.mark.django_db
def test_rule_matcher_ne_and_contains():
    from apps.alerts.models.models import Level

    Level.objects.create(level_id=0, level_name="Critical", level_display_name="严重", level_type="alert")
    Level.objects.create(level_id=1, level_name="Warning", level_display_name="警告", level_type="alert")

    matcher = RuleMatcher({"name": "level_name"})
    ne_ids = matcher.filter_queryset(Level.objects.all(), [[{"key": "name", "operator": "ne", "value": "Critical"}]])
    assert len(ne_ids) == 1
    contains_ids = matcher.filter_queryset(Level.objects.all(), [[{"key": "name", "operator": "contains", "value": "arn"}]])
    assert len(contains_ids) == 1


@pytest.mark.django_db
def test_rule_matcher_empty_rules_returns_all():
    from apps.alerts.models.models import Level

    Level.objects.create(level_id=0, level_name="Critical", level_display_name="严重", level_type="alert")
    matcher = RuleMatcher({"name": "level_name"})
    assert len(matcher.filter_queryset(Level.objects.all(), [])) == 1


def test_rule_matcher_unknown_field_returns_none():
    matcher = RuleMatcher({"name": "level_name"})
    assert matcher.build_single_rule_q({"key": "missing", "operator": "eq", "value": "x"}) is None


def test_rule_matcher_invalid_regex_returns_none():
    matcher = RuleMatcher({"name": "level_name"})
    assert matcher.build_single_rule_q({"key": "name", "operator": "re", "value": "["}) is None


def test_rule_matcher_unknown_operator_returns_none():
    matcher = RuleMatcher({"name": "level_name"})
    assert matcher.build_single_rule_q({"key": "name", "operator": "weird", "value": "x"}) is None


def test_rule_matcher_valid_operators_build_q():
    matcher = RuleMatcher({"name": "level_name"})
    assert matcher.build_single_rule_q({"key": "name", "operator": "eq", "value": "a"}) is not None
    assert matcher.build_single_rule_q({"key": "name", "operator": "not_contains", "value": "a"}) is not None
    assert matcher.build_single_rule_q({"key": "name", "operator": "re", "value": "a.*"}) is not None


# --------------------------------------------------------------------------
# TimeRangeChecker
# --------------------------------------------------------------------------


def _dt(y, m, d, hh, mm, ss):
    return timezone.make_aware(datetime.datetime(y, m, d, hh, mm, ss))


def test_time_range_empty_config_always_true():
    assert TimeRangeChecker({}).is_in_range() is True


def test_time_range_one_within():
    config = {"type": "one", "start_time": "2026-01-01 00:00:00", "end_time": "2026-12-31 23:59:59"}
    assert check_time_range(config, _dt(2026, 6, 1, 12, 0, 0)) is True


def test_time_range_one_outside():
    config = {"type": "one", "start_time": "2026-01-01 00:00:00", "end_time": "2026-01-02 00:00:00"}
    assert check_time_range(config, _dt(2026, 6, 1, 12, 0, 0)) is False


def test_time_range_one_missing_fields_false():
    assert check_time_range({"type": "one", "start_time": "2026-01-01 00:00:00"}, _dt(2026, 6, 1, 12, 0, 0)) is False


def test_time_range_day():
    config = {"type": "day", "start_time": "09:00:00", "end_time": "18:00:00"}
    assert check_time_range(config, _dt(2026, 6, 1, 12, 0, 0)) is True
    assert check_time_range(config, _dt(2026, 6, 1, 20, 0, 0)) is False


def test_time_range_week_matched():
    # 2026-06-01 is a Monday (weekday 1)
    config = {"type": "week", "week_month": [1], "start_time": "00:00:00", "end_time": "23:59:59"}
    assert check_time_range(config, _dt(2026, 6, 1, 12, 0, 0)) is True
    # Not in configured weekday
    config2 = {"type": "week", "week_month": [2], "start_time": "00:00:00", "end_time": "23:59:59"}
    assert check_time_range(config2, _dt(2026, 6, 1, 12, 0, 0)) is False


def test_time_range_month_matched():
    config = {"type": "month", "week_month": [1], "start_time": "00:00:00", "end_time": "23:59:59"}
    assert check_time_range(config, _dt(2026, 6, 1, 12, 0, 0)) is True
    config2 = {"type": "month", "week_month": [15], "start_time": "00:00:00", "end_time": "23:59:59"}
    assert check_time_range(config2, _dt(2026, 6, 1, 12, 0, 0)) is False


def test_time_range_unknown_type_true():
    assert check_time_range({"type": "weird"}, _dt(2026, 6, 1, 12, 0, 0)) is True


def test_extract_time_part():
    assert TimeRangeChecker._extract_time_part("2026-01-01 09:30:00") == "09:30:00"
    assert TimeRangeChecker._extract_time_part("09:30:00") == "09:30:00"


def test_is_day_matched_variants():
    checker = TimeRangeChecker({})
    assert checker._is_day_matched(None, "3") is True
    assert checker._is_day_matched([1, 2, 3], "2") is True
    assert checker._is_day_matched([1, 2], "5") is False
    assert checker._is_day_matched("123", "2") is True
    assert checker._is_day_matched(123, "2") is False
