from datetime import datetime
from types import SimpleNamespace

import pydantic.root_model  # noqa
import pytest
from django.db.models import Q

from apps.log.nats import log as nats_log

# ----------------------- _normalize_positive_int -----------------------


def test_normalize_positive_int_default_for_empty():
    assert nats_log._normalize_positive_int(None, "page", default=1) == 1
    assert nats_log._normalize_positive_int("", "page", default=3) == 3


def test_normalize_positive_int_parses():
    assert nats_log._normalize_positive_int("5", "page") == 5


def test_normalize_positive_int_rejects_non_int():
    with pytest.raises(ValueError, match="必须是整数"):
        nats_log._normalize_positive_int("abc", "page")


def test_normalize_positive_int_rejects_below_one():
    with pytest.raises(ValueError, match="大于等于 1"):
        nats_log._normalize_positive_int(0, "page")


# ----------------------- _normalize_time_value -----------------------


def test_normalize_time_value_parses_string():
    out = nats_log._normalize_time_value("2024-01-02 03:04:05", "start")
    assert out == datetime(2024, 1, 2, 3, 4, 5)


def test_normalize_time_value_empty_raises():
    with pytest.raises(ValueError, match="不能为空"):
        nats_log._normalize_time_value("", "start")


def test_normalize_time_value_non_string_raises():
    with pytest.raises(ValueError, match="时间格式错误"):
        nats_log._normalize_time_value(123, "start")


# ----------------------- _normalize_filter_values -----------------------


def test_normalize_filter_values_empty():
    assert nats_log._normalize_filter_values(None, "x") == []
    assert nats_log._normalize_filter_values("", "x") == []


def test_normalize_filter_values_list_filters_empties():
    assert nats_log._normalize_filter_values([1, "", None, "b"], "x") == ["1", "b"]


def test_normalize_filter_values_csv_string():
    assert nats_log._normalize_filter_values("a, b ,,c", "x") == ["a", "b", "c"]


def test_normalize_filter_values_invalid_type_raises():
    with pytest.raises(ValueError, match="必须是字符串或列表"):
        nats_log._normalize_filter_values({"a": 1}, "x")


# ----------------------- _paginate_items -----------------------


def test_paginate_items_slices_correctly():
    out = nats_log._paginate_items([1, 2, 3, 4, 5], page=2, page_size=2)
    assert out == {"count": 5, "page": 2, "page_size": 2, "items": [3, 4]}


# ----------------------- _build_log_alert_segment -----------------------


def test_build_log_alert_segment_computes_duration():
    alert = SimpleNamespace(
        id=1,
        policy_id=10,
        collect_type_id="ct",
        source_id="s1",
        level="critical",
        value=5,
        content="boom",
        status="open",
        start_event_time=datetime(2024, 1, 1, 0, 0, 0),
        end_event_time=datetime(2024, 1, 1, 0, 1, 0),
        created_at=datetime(2024, 1, 1, 0, 0, 0),
        updated_at=datetime(2024, 1, 1, 0, 1, 0),
    )
    seg = nats_log._build_log_alert_segment(alert)
    assert seg["id"] == 1
    assert seg["duration_seconds"] == 60
    assert seg["start_event_time"] == "2024-01-01T00:00:00"
    assert seg["end_event_time"] == "2024-01-01T00:01:00"


def test_build_log_alert_segment_falls_back_to_created_at():
    created = datetime(2024, 1, 1, 0, 0, 0)
    alert = SimpleNamespace(
        id=2,
        policy_id=None,
        collect_type_id=None,
        source_id="s",
        level="info",
        value=0,
        content="",
        status="closed",
        start_event_time=None,
        end_event_time=None,
        created_at=created,
        updated_at=None,
    )
    seg = nats_log._build_log_alert_segment(alert)
    # segment_start = created_at, segment_end = created_at -> duration 0
    assert seg["duration_seconds"] == 0
    assert seg["start_event_time"] == created.isoformat()


# ----------------------- _apply_log_group_scope -----------------------


def test_apply_log_group_scope_no_user_info_denies():
    from apps.log.utils.log_group import LogGroupQueryBuilder

    assert nats_log._apply_log_group_scope("q", None) == LogGroupQueryBuilder.DENY_ALL_QUERY


def test_apply_log_group_scope_no_groups_denies(mocker):
    from apps.log.utils.log_group import LogGroupQueryBuilder

    mocker.patch.object(nats_log, "_resolve_log_group_scope", return_value=[])
    assert nats_log._apply_log_group_scope("q", {"user": "u"}) == LogGroupQueryBuilder.DENY_ALL_QUERY


def test_apply_log_group_scope_builds_scoped_query(mocker):
    groups = [SimpleNamespace(id="g1", name="g1", rule=None)]
    mocker.patch.object(nats_log, "_resolve_log_group_scope", return_value=groups)
    build = mocker.patch.object(nats_log.LogGroupQueryBuilder, "build_query_with_groups", return_value=("SCOPED", []))
    out = nats_log._apply_log_group_scope("q", {"user": "u"})
    assert out == "SCOPED"
    build.assert_called_once_with("q", ["g1"], resolved_groups=groups)


# ----------------------- _resolve_log_group_scope -----------------------


def test_resolve_log_group_scope_returns_empty_without_user_info():
    assert nats_log._resolve_log_group_scope(None) == []


def test_resolve_log_group_scope_returns_empty_without_username():
    assert nats_log._resolve_log_group_scope({"team": "1"}) == []
    assert nats_log._resolve_log_group_scope({"user": "u"}) == []  # 缺 team


def test_resolve_log_group_scope_superuser_is_current_team_scoped(mocker):
    groups = [SimpleNamespace(id="g1", name="g1", rule=None)]
    mocker.patch(
        "apps.rpc.system_mgmt.SystemMgmt.get_authorized_groups_scoped",
        return_value={"result": True, "data": [1], "is_superuser": True},
    )
    qs = mocker.MagicMock()
    qs.filter.return_value = qs
    qs.distinct.return_value = qs
    qs.only.return_value = groups
    mocker.patch.object(nats_log.LogGroup.objects, "filter", return_value=qs)

    assert (
        nats_log._resolve_log_group_scope(
            {
                "user": "u",
                "domain": "domain.com",
                "team": 1,
                "include_children": False,
                "is_superuser": False,
            }
        )
        == groups
    )
    qs.filter.assert_not_called()


@pytest.mark.parametrize("endpoint", ["search", "hits"])
def test_log_query_forged_superuser_still_applies_object_permission(mocker, endpoint):
    group = SimpleNamespace(id="group-a", name="group-a", rule={})
    mocker.patch(
        "apps.rpc.system_mgmt.SystemMgmt.get_authorized_groups_scoped",
        return_value={"result": True, "data": [1], "is_superuser": False},
    )
    permission_rpc = mocker.patch.object(
        nats_log,
        "get_permission_rules",
        return_value={"team": [], "instance": []},
    )

    forged_superuser_queryset = mocker.MagicMock()
    forged_superuser_queryset.distinct.return_value = forged_superuser_queryset
    forged_superuser_queryset.only.return_value = [group]
    mocker.patch.object(
        nats_log.LogGroup.objects,
        "filter",
        return_value=forged_superuser_queryset,
    )

    permission_queryset = mocker.MagicMock()
    permission_queryset.filter.return_value = permission_queryset
    permission_queryset.distinct.return_value = permission_queryset
    permission_queryset.only.return_value = []
    mocker.patch.object(
        nats_log,
        "permission_filter",
        return_value=permission_queryset,
    )
    mocker.patch.object(
        nats_log.LogGroupQueryBuilder,
        "build_query_with_groups",
        return_value=("SCOPED", []),
    )
    mocker.patch.object(nats_log, "format_time_iso", side_effect=lambda value: value)
    victoria_logs = mocker.patch.object(nats_log, "VictoriaMetricsAPI")
    victoria_logs.return_value.query.return_value = [{"message": "leaked"}]
    victoria_logs.return_value.hits.return_value = {"hits": [{"timestamps": ["t1"], "values": [1]}]}
    user_info = {
        "user": "ordinary-user",
        "domain": "domain.com",
        "team": 1,
        "include_children": False,
        "is_superuser": True,
    }

    if endpoint == "search":
        result = nats_log.log_search("q", ("start", "end"), user_info=user_info)
    else:
        result = nats_log.log_hits(
            "q",
            ("start", "end"),
            "host",
            user_info=user_info,
        )

    assert result == {"result": True, "data": [], "message": ""}
    permission_rpc.assert_called_once()
    victoria_logs.assert_not_called()


def test_resolve_log_group_scope_filters_accessible_groups(mocker):
    groups = [SimpleNamespace(id="g1", name="g1", rule=None)]
    mocker.patch(
        "apps.rpc.system_mgmt.SystemMgmt.get_authorized_groups_scoped",
        return_value={"result": True, "data": [1]},
    )
    mocker.patch.object(nats_log, "get_permission_rules", return_value={"some": "rule"})
    qs = mocker.MagicMock()
    qs.filter.return_value = qs
    qs.distinct.return_value = qs
    qs.only.return_value = groups
    mocker.patch.object(nats_log, "permission_filter", return_value=qs)
    out = nats_log._resolve_log_group_scope(
        {
            "user": "u",
            "domain": "domain.com",
            "team": 1,
            "include_children": False,
            "is_superuser": False,
        }
    )
    assert out == groups


def test_resolve_log_group_scope_non_dict_permission_defaults_empty(mocker):
    mocker.patch(
        "apps.rpc.system_mgmt.SystemMgmt.get_authorized_groups_scoped",
        return_value={"result": True, "data": [1]},
    )
    mocker.patch.object(nats_log, "get_permission_rules", return_value="not-a-dict")
    captured = {}

    def fake_filter(model, permission, **kwargs):
        captured["permission"] = permission
        qs = mocker.MagicMock()
        qs.filter.return_value = qs
        qs.distinct.return_value = qs
        qs.only.return_value = []
        return qs

    mocker.patch.object(nats_log, "permission_filter", side_effect=fake_filter)
    nats_log._resolve_log_group_scope(
        {
            "user": "u",
            "domain": "domain.com",
            "team": 1,
            "include_children": False,
            "is_superuser": False,
        }
    )
    assert captured["permission"] == {}


def test_resolve_log_group_scope_rejects_forged_current_team_before_permission(mocker):
    scope_rpc = mocker.patch(
        "apps.rpc.system_mgmt.SystemMgmt.get_authorized_groups_scoped",
        return_value={"result": True, "data": []},
    )
    permission_rpc = mocker.patch.object(nats_log, "get_permission_rules")

    assert (
        nats_log._resolve_log_group_scope(
            {
                "user": "u",
                "domain": "domain.com",
                "team": 2,
                "include_children": False,
                "is_superuser": False,
            }
        )
        == []
    )
    scope_rpc.assert_called_once()
    permission_rpc.assert_not_called()


def test_resolve_log_group_scope_rejects_forged_superuser_before_permission(mocker):
    scope_rpc = mocker.patch(
        "apps.rpc.system_mgmt.SystemMgmt.get_authorized_groups_scoped",
        return_value={"result": True, "data": []},
    )
    permission_rpc = mocker.patch.object(nats_log, "get_permission_rules")

    result = nats_log._resolve_log_group_scope(
        {
            "user": "ordinary-user",
            "domain": "domain.com",
            "team": 2,
            "include_children": False,
            "is_superuser": True,
        }
    )

    assert result == []
    scope_rpc.assert_called_once()
    permission_rpc.assert_not_called()


# ----------------------- log_search nats endpoint -----------------------


def test_log_search_returns_data(mocker):
    mocker.patch.object(nats_log, "_apply_log_group_scope", return_value="SCOPED")
    mocker.patch.object(nats_log, "format_time_iso", side_effect=lambda v: f"iso:{v}")
    vm = mocker.patch.object(nats_log, "VictoriaMetricsAPI").return_value
    vm.query.return_value = [{"a": 1}]
    out = nats_log.log_search("q", ("s", "e"), limit=5, user_info={"user": "u"})
    assert out == {"result": True, "data": [{"a": 1}], "message": ""}
    vm.query.assert_called_once_with("SCOPED", "iso:s", "iso:e", 5)


def test_log_search_invalid_limit_returns_error(mocker):
    mocker.patch.object(nats_log, "_apply_log_group_scope", return_value="SCOPED")
    mocker.patch.object(nats_log, "format_time_iso", side_effect=lambda v: v)
    out = nats_log.log_search("q", ("s", "e"), limit="not-int")
    assert out["result"] is False
    assert out["data"] == []
    assert "整数" in out["message"]


@pytest.mark.parametrize("user_info", [None, {}, {"user": "incomplete"}])
def test_log_search_denied_scope_returns_empty_without_victorialogs(
    mocker,
    user_info,
):
    mocker.patch.object(nats_log, "format_time_iso", side_effect=lambda value: value)
    victoria_logs = mocker.patch.object(nats_log, "VictoriaMetricsAPI")

    result = nats_log.log_search(
        "q",
        ("start", "end"),
        user_info=user_info,
    )

    assert result == {"result": True, "data": [], "message": ""}
    victoria_logs.assert_not_called()


@pytest.mark.parametrize("user_info", [None, {}, {"user": "incomplete"}])
def test_log_hits_denied_scope_returns_empty_without_victorialogs(
    mocker,
    user_info,
):
    mocker.patch.object(nats_log, "format_time_iso", side_effect=lambda value: value)
    victoria_logs = mocker.patch.object(nats_log, "VictoriaMetricsAPI")

    result = nats_log.log_hits(
        "q",
        ("start", "end"),
        "host",
        user_info=user_info,
    )

    assert result == {"result": True, "data": [], "message": ""}
    victoria_logs.assert_not_called()


# ----------------------- log_hits nats endpoint -----------------------


def test_log_hits_flattens_timestamps_and_values(mocker):
    mocker.patch.object(nats_log, "_apply_log_group_scope", return_value="SCOPED")
    mocker.patch.object(nats_log, "format_time_iso", side_effect=lambda v: v)
    vm = mocker.patch.object(nats_log, "VictoriaMetricsAPI").return_value
    vm.hits.return_value = {"hits": [{"timestamps": ["t1", "t2"], "values": [1, 2]}]}
    out = nats_log.log_hits("q", ("s", "e"), "host", fields_limit=5)
    assert out["result"] is True
    assert out["data"] == [{"name": "t1", "value": 1}, {"name": "t2", "value": 2}]


def test_log_hits_invalid_fields_limit(mocker):
    mocker.patch.object(nats_log, "_apply_log_group_scope", return_value="SCOPED")
    mocker.patch.object(nats_log, "format_time_iso", side_effect=lambda v: v)
    out = nats_log.log_hits("q", ("s", "e"), "host", fields_limit="bad")
    assert out["result"] is False
    assert "整数" in out["message"]


# ----------------------- get_vmlogs_disk_usage nats endpoint -----------------------


def test_get_vmlogs_disk_usage(mocker):
    vm = mocker.patch.object(nats_log, "VictoriaMetricsAPI").return_value
    vm.get_disk_usage.return_value = {"used_gb": 1.5}
    out = nats_log.get_vmlogs_disk_usage()
    assert out == {"result": True, "data": {"used_gb": 1.5}, "message": ""}


# ----------------------- query_log_alert_segments validation -----------------------


def test_query_log_alert_segments_missing_field():
    out = nats_log.query_log_alert_segments({"collect_type_id": "ct", "start": "x"})
    assert out["result"] is False
    assert "end" in out["message"]


def test_query_log_alert_segments_bad_time_format():
    out = nats_log.query_log_alert_segments({"collect_type_id": "ct", "start": "bad", "end": "2024-01-02 00:00:00"})
    assert out["result"] is False


def test_query_log_alert_segments_start_after_end():
    out = nats_log.query_log_alert_segments(
        {
            "collect_type_id": "ct",
            "start": "2024-01-02 00:00:00",
            "end": "2024-01-01 00:00:00",
        }
    )
    assert out["result"] is False
    assert "开始时间不能大于结束时间" in out["message"]


def test_query_log_alert_segments_page_size_too_large():
    out = nats_log.query_log_alert_segments(
        {
            "collect_type_id": "ct",
            "start": "2024-01-01 00:00:00",
            "end": "2024-01-02 00:00:00",
            "page_size": 999,
        }
    )
    assert out["result"] is False
    assert "page_size 不能大于 500" in out["message"]


def test_query_log_alert_segments_empty_policy_ids_returns_empty_page(mocker):
    mocker.patch.object(nats_log, "_get_log_policy_ids", return_value=([], None))
    out = nats_log.query_log_alert_segments(
        {
            "collect_type_id": "ct",
            "start": "2024-01-01 00:00:00",
            "end": "2024-01-02 00:00:00",
        },
        user_info={"user": "u", "team": "t"},
    )
    assert out["result"] is True
    assert out["data"]["items"] == []


def test_query_log_alert_segments_propagates_policy_error(mocker):
    err = {"result": False, "data": [], "message": "缺少用户或组织信息"}
    mocker.patch.object(nats_log, "_get_log_policy_ids", return_value=([], err))
    out = nats_log.query_log_alert_segments(
        {
            "collect_type_id": "ct",
            "start": "2024-01-01 00:00:00",
            "end": "2024-01-02 00:00:00",
        }
    )
    assert out == err


def test_query_log_alert_segments_filters_by_overlapping_event_time(mocker):
    mocker.patch.object(nats_log, "_get_log_policy_ids", return_value=(["policy-1"], None))
    queryset = mocker.MagicMock()
    filtered_queryset = queryset.filter.return_value
    mocker.patch.object(nats_log.Alert.objects, "filter", return_value=queryset)
    mocker.patch.object(
        nats_log,
        "_build_paginated_alert_segments",
        return_value={"count": 0, "page": 1, "page_size": 100, "items": []},
    )

    out = nats_log.query_log_alert_segments(
        {
            "collect_type_id": "ct",
            "start": "2024-01-01 01:00:00",
            "end": "2024-01-01 02:00:00",
        }
    )

    assert out["result"] is True
    queryset.filter.assert_called_once_with(
        Q(end_event_time__isnull=True) | Q(end_event_time__gte=datetime(2024, 1, 1, 1, 0, 0)),
        start_event_time__lte=datetime(2024, 1, 1, 2, 0, 0),
    )
    nats_log._build_paginated_alert_segments.assert_called_once_with(filtered_queryset, 1, 100)
