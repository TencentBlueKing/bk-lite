import json

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Alert, Event
from apps.alerts.views.alert import AlertModelViewSet


@pytest.fixture
def superuser(authenticated_user):
    authenticated_user.is_superuser = True
    return authenticated_user


@pytest.fixture(autouse=True)
def grant_alert_scope(monkeypatch):
    monkeypatch.setattr(
        "apps.core.utils.viewset_utils.get_permission_rules",
        lambda *args, **kwargs: {"instance": [], "team": ["1"]},
    )


def _normalized_sql(sql):
    return sql.lower().replace('"', "").replace("`", "").replace("[", "").replace("]", "")


@pytest.mark.django_db
def test_alert_list_counts_events_without_loading_event_details(superuser):
    source = AlertSource.objects.create(
        name="source",
        source_id="alert-list-query-source",
        source_type="restful",
        secret="secret",
    )
    alert = Alert.objects.create(
        alert_id="alert-list-query",
        level="0",
        title="title",
        content="content",
        fingerprint="fingerprint",
        team=[1],
    )
    events = [
        Event(
            source=source,
            raw_data={"payload": index},
            title=f"event-{index}",
            level="0",
            start_time=timezone.now(),
            event_id=f"alert-list-query-event-{index}",
            team=[1],
        )
        for index in range(3)
    ]
    Event.objects.bulk_create(events)
    alert.events.add(*events)

    request = APIRequestFactory().get("/alerts/?page=1&page_size=20")
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=superuser)

    with CaptureQueriesContext(connection) as captured:
        response = AlertModelViewSet.as_view({"get": "list"})(request)
        if hasattr(response, "render"):
            response.render()

    payload = json.loads(response.content)["data"]
    item = next(item for item in payload["items"] if item["alert_id"] == alert.alert_id)
    assert item["event_count"] == 3
    assert "source_names" not in item

    event_detail_queries = [query["sql"] for query in captured.captured_queries if "from alerts_event " in _normalized_sql(query["sql"])]
    assert not event_detail_queries, "alert list fetched Event detail rows:\n" + "\n".join(event_detail_queries)
