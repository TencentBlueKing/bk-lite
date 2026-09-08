"""告警详情和关联事件接口的监控对象快照契约。"""

import json

import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Alert, Event
from apps.alerts.serializers import AlertModelSerializer, EventModelSerializer
from apps.alerts.views.alert import AlertModelViewSet

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def _request(path, user, team="1"):
    request = APIRequestFactory().get(path)
    request.COOKIES["current_team"] = team
    force_authenticate(request, user=user)
    return request


def _render(response):
    response.render()
    return json.loads(response.rendered_content)


@pytest.fixture(autouse=True)
def _grant_permissions(monkeypatch):
    monkeypatch.setattr(
        "apps.core.utils.viewset_utils.get_permission_rules",
        lambda *args, **kwargs: {"instance": [], "team": ["1"]},
    )


def test_alert_retrieve_returns_full_monitor_object_collection(authenticated_user):
    authenticated_user.is_superuser = True
    alert = Alert.objects.create(
        alert_id="ALERT-SNAPSHOT-VIEW-1",
        level="1",
        title="聚合监控告警",
        content="desc",
        fingerprint="snapshot-view-1",
        team=[1],
        monitor_objects=[
            {
                "monitor_id": "0001",
                "cmdb_id": "xxxx1",
                "resource_type": "Host",
                "resource_name": "ip1",
            },
            {
                "monitor_id": "0002",
                "cmdb_id": None,
                "resource_type": "Switch",
                "resource_name": "ip2",
            },
        ],
    )
    request = _request(
        f"/alerts/{alert.id}/",
        authenticated_user,
    )

    response = AlertModelViewSet.as_view({"get": "retrieve"})(
        request,
        pk=str(alert.id),
    )
    payload = _render(response)

    assert response.status_code == 200
    assert payload["data"]["monitor_objects"] == alert.monitor_objects


def test_alert_events_returns_each_event_identity_snapshot(authenticated_user):
    authenticated_user.is_superuser = True
    source = AlertSource.objects.create(
        name="NATS",
        source_id="nats-snapshot-view",
        source_type="nats",
        secret="x",
    )
    alert = Alert.objects.create(
        alert_id="ALERT-SNAPSHOT-EVENTS-1",
        level="1",
        title="聚合监控告警",
        content="desc",
        fingerprint="snapshot-events-1",
        team=[1],
    )
    event = Event.objects.create(
        source=source,
        raw_data={},
        title="CPU high",
        level="1",
        start_time=timezone.now(),
        event_id="EVENT-SNAPSHOT-VIEW-1",
        monitor_id="monitor-view-1",
        cmdb_id="cmdb-view-1",
        resource_id="monitor-view-1",
        resource_name="host-view-1",
        resource_type="Host",
        team=[1],
    )
    alert.events.add(event)
    request = _request(
        f"/alerts/{alert.id}/events/",
        authenticated_user,
    )

    response = AlertModelViewSet.as_view({"get": "events"})(
        request,
        pk=str(alert.id),
    )
    payload = _render(response)
    data = payload["data"]
    items = data["items"] if isinstance(data, dict) else data

    assert response.status_code == 200
    assert (items[0]["monitor_id"], items[0]["cmdb_id"]) == (
        "monitor-view-1",
        "cmdb-view-1",
    )


def test_event_pagination_does_not_truncate_alert_monitor_objects(authenticated_user):
    authenticated_user.is_superuser = True
    source = AlertSource.objects.create(
        name="NATS",
        source_id="nats-snapshot-pagination",
        source_type="nats",
        secret="x",
    )
    monitor_objects = [
        {
            "monitor_id": "monitor-page-1",
            "cmdb_id": "cmdb-page-1",
            "resource_type": "Host",
            "resource_name": "host-page-1",
        },
        {
            "monitor_id": "monitor-page-2",
            "cmdb_id": "cmdb-page-2",
            "resource_type": "Switch",
            "resource_name": "switch-page-2",
        },
    ]
    alert = Alert.objects.create(
        alert_id="ALERT-SNAPSHOT-PAGE-1",
        level="1",
        title="聚合监控告警",
        content="desc",
        fingerprint="snapshot-page-1",
        team=[1],
        monitor_objects=monitor_objects,
    )
    for index in range(3):
        event = Event.objects.create(
            source=source,
            raw_data={},
            title=f"event-{index}",
            level="1",
            start_time=timezone.now(),
            event_id=f"EVENT-SNAPSHOT-PAGE-{index}",
            monitor_id=f"monitor-page-{(index % 2) + 1}",
            team=[1],
        )
        alert.events.add(event)

    events_request = _request(
        f"/alerts/{alert.id}/events/?page=1&page_size=1",
        authenticated_user,
    )
    events_response = AlertModelViewSet.as_view({"get": "events"})(
        events_request,
        pk=str(alert.id),
    )
    events_payload = _render(events_response)
    detail_request = _request(f"/alerts/{alert.id}/", authenticated_user)
    detail_response = AlertModelViewSet.as_view({"get": "retrieve"})(
        detail_request,
        pk=str(alert.id),
    )
    detail_payload = _render(detail_response)

    assert len(events_payload["data"]["items"]) == 1
    assert detail_payload["data"]["monitor_objects"] == monitor_objects


def test_cross_organization_user_cannot_read_event_identity_snapshot(
    authenticated_user,
):
    authenticated_user.is_superuser = False
    authenticated_user.permission = {"alarm": {"Alarms-View"}}
    source = AlertSource.objects.create(
        name="NATS",
        source_id="nats-snapshot-permission",
        source_type="nats",
        secret="x",
    )
    alert = Alert.objects.create(
        alert_id="ALERT-SNAPSHOT-PERMISSION-1",
        level="1",
        title="跨组织告警",
        content="desc",
        fingerprint="snapshot-perm-1",
        team=[2],
        monitor_objects=[
            {
                "monitor_id": "secret-monitor",
                "cmdb_id": "secret-cmdb",
                "resource_type": "Host",
                "resource_name": "secret-host",
            }
        ],
    )
    event = Event.objects.create(
        source=source,
        raw_data={},
        title="secret event",
        level="1",
        start_time=timezone.now(),
        event_id="EVENT-SNAPSHOT-PERMISSION-1",
        monitor_id="secret-monitor",
        cmdb_id="secret-cmdb",
        team=[2],
    )
    alert.events.add(event)
    request = _request(
        f"/alerts/{alert.id}/events/",
        authenticated_user,
        team="1",
    )

    response = AlertModelViewSet.as_view({"get": "events"})(
        request,
        pk=str(alert.id),
    )

    assert response.status_code == 404


def test_legacy_alert_retrieve_returns_empty_monitor_objects(authenticated_user):
    authenticated_user.is_superuser = True
    alert = Alert.objects.create(
        alert_id="ALERT-SNAPSHOT-LEGACY-1",
        level="1",
        title="旧告警",
        content="desc",
        fingerprint="snapshot-legacy-1",
        team=[1],
        resource_id="legacy-resource",
        resource_type="legacy-type",
        resource_name="legacy-name",
    )
    request = _request(f"/alerts/{alert.id}/", authenticated_user)

    response = AlertModelViewSet.as_view({"get": "retrieve"})(
        request,
        pk=str(alert.id),
    )
    payload = _render(response)

    assert payload["data"]["monitor_objects"] == []


def test_identity_snapshot_fields_are_read_only_in_crud_serializers(
    authenticated_user,
):
    request = _request("/", authenticated_user)
    request.user = authenticated_user
    alert_serializer = AlertModelSerializer(context={"request": request})
    event_serializer = EventModelSerializer(context={"request": request})

    assert alert_serializer.fields["monitor_objects"].read_only is True
    assert event_serializer.fields["monitor_id"].read_only is True
    assert event_serializer.fields["cmdb_id"].read_only is True
