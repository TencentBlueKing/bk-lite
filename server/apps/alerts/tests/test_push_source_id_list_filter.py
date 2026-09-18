"""告警/事件列表按监控源 IN 筛选：Alert 走快照，Event 走单值。"""
import json

import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.alerts.filters.alert import AlertModelFilter
from apps.alerts.filters.event import EventModelFilter
from apps.alerts.models import Alert, AlertSource, Event

pytestmark = [pytest.mark.django_db]


def make_alert(alert_id, push_source_ids):
    return Alert.objects.create(
        alert_id=alert_id,
        fingerprint=alert_id,
        title="CPU",
        content="",
        level="1",
        team=[1],
        push_source_ids=push_source_ids,
    )


def test_alert_list_filters_snapshot_any_of():
    hit = make_alert("hit", ["prod", "test"])
    make_alert("miss", ["other"])
    make_alert("empty", [])
    related_only = make_alert("related", [])
    source = AlertSource.objects.create(name="src", source_id="src-1", source_type="restful", secret="test")
    related_only.events.add(
        Event.objects.create(
            source=source,
            event_id="event-related",
            title="CPU",
            level="1",
            start_time=timezone.now(),
            raw_data={},
            push_source_id="prod",
        )
    )
    qs = AlertModelFilter({"push_source_ids": json.dumps(["prod", "001"])}, queryset=Alert.objects.all()).qs
    assert set(qs) == {hit}


def test_alert_list_does_not_match_json_as_text():
    make_alert("prefix", ["prod-1"])
    qs = AlertModelFilter({"push_source_ids": json.dumps(["prod"])}, queryset=Alert.objects.all()).qs
    assert not qs.exists()


def test_alert_list_skips_empty_param():
    first = make_alert("a", ["prod"])
    second = make_alert("b", [])
    assert set(AlertModelFilter({}, queryset=Alert.objects.all()).qs) == {first, second}
    assert set(AlertModelFilter({"push_source_ids": ""}, queryset=Alert.objects.all()).qs) == {first, second}


def test_alert_list_rejects_invalid_payload():
    with pytest.raises(ValidationError):
        AlertModelFilter({"push_source_ids": "prod"}, queryset=Alert.objects.all()).qs


def make_event(event_id, push_source_id, source=None):
    if source is None:
        source = AlertSource.objects.create(
            name=f"src-{event_id}",
            source_id=f"src-{event_id}",
            source_type="restful",
            secret="test",
        )
    return Event.objects.create(
        source=source,
        event_id=event_id,
        title="CPU",
        level="1",
        start_time=timezone.now(),
        raw_data={},
        push_source_id=push_source_id,
    )


def test_event_list_filters_push_source_id_in():
    source = AlertSource.objects.create(name="src", source_id="src-1", source_type="restful", secret="test")
    hit = make_event("hit", "prod", source=source)
    make_event("miss", "other", source=source)
    make_event("empty", "", source=source)
    qs = EventModelFilter({"push_source_ids": json.dumps(["prod", "001"])}, queryset=Event.objects.all()).qs
    assert list(qs) == [hit]


def test_event_list_exact_push_source_id_unaffected():
    source = AlertSource.objects.create(name="src", source_id="src-1", source_type="restful", secret="test")
    hit = make_event("hit", "prod", source=source)
    make_event("other", "other", source=source)
    qs = EventModelFilter({"push_source_id": "prod"}, queryset=Event.objects.all()).qs
    assert list(qs) == [hit]


def test_event_list_skips_empty_param():
    source = AlertSource.objects.create(name="src", source_id="src-1", source_type="restful", secret="test")
    first = make_event("a", "prod", source=source)
    second = make_event("b", "other", source=source)
    assert set(EventModelFilter({}, queryset=Event.objects.all()).qs) == {first, second}
    assert set(EventModelFilter({"push_source_ids": ""}, queryset=Event.objects.all()).qs) == {first, second}


def test_event_list_rejects_invalid_payload():
    with pytest.raises(ValidationError) as exc_info:
        EventModelFilter({"push_source_ids": "prod"}, queryset=Event.objects.all()).qs
    assert exc_info.value.detail == {"push_source_ids": "监控源须为 JSON 字符串数组"}
