"""告警中心 permission_scope 组织范围过滤覆盖测试。

对照 spec/prd/告警中心：告警/事故/事件按组织(team)隔离，支持包含子组织。
"""

from types import SimpleNamespace

import pytest
from rest_framework.exceptions import PermissionDenied

from apps.alerts.models.models import Alert, Incident
from apps.alerts.utils import permission_scope as ps


def _request(current_team="1", is_superuser=False, group_list=None, include_children="0", group_tree=None, user=True):
    cookies = {"include_children": include_children}
    if current_team is not None:
        cookies["current_team"] = current_team
    u = None
    if user:
        u = SimpleNamespace(
            is_superuser=is_superuser,
            group_list=group_list if group_list is not None else [{"id": 1}],
            group_tree=group_tree or [],
        )
    return SimpleNamespace(COOKIES=cookies, user=u)


# --------------------------------------------------------------------------
# get_current_team_from_request
# --------------------------------------------------------------------------


def test_get_current_team_valid():
    assert ps.get_current_team_from_request(_request(current_team="5")) == 5


def test_get_current_team_missing_not_required():
    assert ps.get_current_team_from_request(_request(current_team=None)) is None


def test_get_current_team_missing_required_returns_zero():
    assert ps.get_current_team_from_request(_request(current_team=None), required=True) == 0


def test_get_current_team_invalid_returns_none():
    assert ps.get_current_team_from_request(_request(current_team="abc")) is None


# --------------------------------------------------------------------------
# normalize_team_ids
# --------------------------------------------------------------------------


def test_normalize_team_ids_valid():
    assert ps.normalize_team_ids([1, "2", 3]) == [1, 2, 3]


def test_normalize_team_ids_empty():
    assert ps.normalize_team_ids(None) == []
    assert ps.normalize_team_ids("") == []


def test_normalize_team_ids_non_list_raises():
    with pytest.raises(ValueError):
        ps.normalize_team_ids("1,2")


def test_normalize_team_ids_bad_element_raises():
    with pytest.raises(ValueError):
        ps.normalize_team_ids([1, "x"])


# --------------------------------------------------------------------------
# get_query_group_ids
# --------------------------------------------------------------------------


def test_get_query_group_ids_superuser_single_team():
    request = _request(current_team="3", is_superuser=True)
    assert ps.get_query_group_ids(request) == [3]


def test_get_query_group_ids_no_team_empty():
    assert ps.get_query_group_ids(_request(current_team=None)) == []


def test_get_query_group_ids_unauthorized_raises():
    request = _request(current_team="9", is_superuser=False, group_list=[{"id": 1}])
    with pytest.raises(PermissionDenied):
        ps.get_query_group_ids(request)


def test_get_query_group_ids_include_children():
    tree = [{"id": 1, "subGroups": [{"id": 2, "subGroups": [{"id": 3}]}]}]
    request = _request(current_team="1", is_superuser=True, include_children="1", group_tree=tree)
    result = ps.get_query_group_ids(request)
    assert set(result) == {1, 2, 3}


# --------------------------------------------------------------------------
# extract_child_group_ids
# --------------------------------------------------------------------------


def test_extract_child_group_ids_nested():
    tree = [{"id": 1, "subGroups": [{"id": 2, "subGroups": [{"id": 3}]}, {"id": 4}]}]
    assert set(ps.extract_child_group_ids(tree, 1)) == {1, 2, 3, 4}


def test_extract_child_group_ids_target_not_found():
    tree = [{"id": 1, "subGroups": []}]
    assert ps.extract_child_group_ids(tree, 99) == []


# --------------------------------------------------------------------------
# apply_team_scope_with_group_ids
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_apply_team_scope_empty_group_ids_returns_none():
    Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp", team=[1])
    result = ps.apply_team_scope_with_group_ids(Alert.objects.all(), [])
    assert result.count() == 0


@pytest.mark.django_db
def test_apply_team_scope_filters_by_team():
    Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp", team=[1])
    Alert.objects.create(alert_id="A2", level="0", title="t", content="c", fingerprint="fp", team=[2])
    result = ps.apply_team_scope_with_group_ids(Alert.objects.all(), [1])
    ids = set(result.values_list("alert_id", flat=True))
    assert ids == {"A1"}


# --------------------------------------------------------------------------
# filter_*_queryset_for_request
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_filter_alert_queryset_no_user_returns_none():
    Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp", team=[1])
    request = _request(user=False)
    assert ps.filter_alert_queryset_for_request(Alert.objects.all(), request).count() == 0


@pytest.mark.django_db
def test_filter_alert_queryset_scoped():
    Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp", team=[1])
    Alert.objects.create(alert_id="A2", level="0", title="t", content="c", fingerprint="fp", team=[2])
    request = _request(current_team="1", is_superuser=True)
    result = ps.filter_alert_queryset_for_request(Alert.objects.all(), request)
    assert set(result.values_list("alert_id", flat=True)) == {"A1"}


@pytest.mark.django_db
def test_filter_incident_queryset_scoped():
    Incident.objects.create(incident_id="I1", level="0", title="t", fingerprint="fp", team=[1])
    Incident.objects.create(incident_id="I2", level="0", title="t", fingerprint="fp", team=[2])
    request = _request(current_team="2", is_superuser=True)
    result = ps.filter_incident_queryset_for_request(Incident.objects.all(), request)
    assert set(result.values_list("incident_id", flat=True)) == {"I2"}


@pytest.mark.django_db
def test_filter_event_queryset_no_user_returns_none():
    from apps.alerts.models.models import Event

    request = _request(user=False)
    assert ps.filter_event_queryset_for_request(Event.objects.all(), request).count() == 0


@pytest.mark.django_db
def test_filter_event_queryset_scoped():
    from django.utils import timezone

    from apps.alerts.models.alert_source import AlertSource
    from apps.alerts.models.models import Event

    src = AlertSource.objects.create(name="s", source_id="s1", source_type="restful", secret="x")
    Event.objects.create(source=src, raw_data={}, title="t", level="0", start_time=timezone.now(), event_id="E1", team=[1])
    Event.objects.create(source=src, raw_data={}, title="t", level="0", start_time=timezone.now(), event_id="E2", team=[2])
    request = _request(current_team="1", is_superuser=True)
    result = ps.filter_event_queryset_for_request(Event.objects.all(), request)
    assert set(result.values_list("event_id", flat=True)) == {"E1"}


@pytest.mark.django_db
def test_filter_operator_log_no_team_returns_none():
    from apps.alerts.models.operator_log import OperatorLog

    request = _request(current_team=None, is_superuser=True)
    assert ps.filter_operator_log_queryset_for_request(OperatorLog.objects.all(), request).count() == 0


@pytest.mark.django_db
def test_filter_operator_log_scoped_to_alert():
    from apps.alerts.constants.constants import LogTargetType
    from apps.alerts.models.operator_log import OperatorLog

    Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp", team=[1])
    OperatorLog.objects.create(action="add", target_type=LogTargetType.ALERT, operator="u", target_id="A1", overview="x")
    OperatorLog.objects.create(action="add", target_type=LogTargetType.ALERT, operator="u", target_id="A-other", overview="x")
    request = _request(current_team="1", is_superuser=True)
    result = ps.filter_operator_log_queryset_for_request(OperatorLog.objects.all(), request)
    assert result.count() == 1


@pytest.mark.django_db
def test_apply_team_scope_for_request():
    Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp", team=[1])
    Alert.objects.create(alert_id="A2", level="0", title="t", content="c", fingerprint="fp", team=[2])
    request = _request(current_team="1", is_superuser=True)
    result = ps.apply_team_scope_for_request(Alert.objects.all(), request)
    assert set(result.values_list("alert_id", flat=True)) == {"A1"}


# --------------------------------------------------------------------------
# _build_team_query / _filter_json_membership_fallback
# --------------------------------------------------------------------------


def test_build_team_query_empty():
    from django.db.models import Q

    assert ps._build_team_query("team", []) == Q()


def test_build_team_query_has_children():
    q = ps._build_team_query("team", [1, 2])
    assert q.children  # 非空 Q


@pytest.mark.django_db
def test_filter_json_membership_fallback_matches():
    Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp", team=[1])
    Alert.objects.create(alert_id="A2", level="0", title="t", content="c", fingerprint="fp", team=[2])
    result = ps._filter_json_membership_fallback(Alert.objects.all(), "team", [1])
    assert set(result.values_list("alert_id", flat=True)) == {"A1"}


@pytest.mark.django_db
def test_filter_json_membership_fallback_empty_expected():
    Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp", team=[1])
    result = ps._filter_json_membership_fallback(Alert.objects.all(), "team", [None, ""])
    assert result.count() == 0
