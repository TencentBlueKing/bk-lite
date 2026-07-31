from datetime import timedelta

import pytest
from django.apps import apps as django_apps
from django.utils import timezone

from apps.apm.adapters.alerts import reconcile_apm_alert_source
from apps.apm.constants import APM_ALERT_PUSHER, APM_ALERT_SOURCE_ID
from apps.apm.services.events import DjangoApmEventReader


pytestmark = pytest.mark.django_db


def test_dedicated_apm_source_ingests_trusted_event_and_event_view_stays_scoped():
    if not django_apps.is_installed("apps.alerts"):
        pytest.skip("Alerts app is not installed in the focused APM test profile")

    from apps.alerts.constants.constants import LevelType
    from apps.alerts.models.models import Event, Level
    from apps.alerts.nats.nats import receive_alert_events

    for level_id in (0, 1, 2, 3):
        Level.objects.create(
            level_id=level_id,
            level_name=f"L{level_id}",
            level_display_name=f"等级{level_id}",
            level_type=LevelType.EVENT,
        )
    source, _ = reconcile_apm_alert_source()
    occurred_at = timezone.now().replace(microsecond=0)
    event = {
        "title": "APM checkout 错误率触发",
        "description": "checkout production error_rate=0.12",
        "level": "1",
        "action": "created",
        "external_id": "apm-alert-1",
        "start_time": str(int(occurred_at.timestamp())),
        "service": "checkout",
        "item": "error_rate",
        "value": 0.12,
        "resource_id": "service-1",
        "resource_type": "apm_service",
        "resource_name": "shop/checkout",
        "organizations": [10],
        "labels": {"policy_id": "policy-1", "environment": "production"},
    }

    response = receive_alert_events(
        source_id=APM_ALERT_SOURCE_ID,
        pusher=APM_ALERT_PUSHER,
        events=[event],
    )

    assert response["result"] is True
    persisted = Event.objects.get(external_id="apm-alert-1")
    assert persisted.source_id == source.id
    assert persisted.push_source_id == APM_ALERT_PUSHER
    assert persisted.team == [10]

    reader = DjangoApmEventReader()
    visible = reader.list(
        organization_id=10,
        started_at=occurred_at - timedelta(minutes=1),
        ended_at=occurred_at + timedelta(minutes=1),
    )
    hidden = reader.list(
        organization_id=20,
        started_at=occurred_at - timedelta(minutes=1),
        ended_at=occurred_at + timedelta(minutes=1),
    )
    assert [item["external_id"] for item in visible] == ["apm-alert-1"]
    assert hidden == []
