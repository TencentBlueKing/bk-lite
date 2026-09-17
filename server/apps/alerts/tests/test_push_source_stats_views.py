"""集成源详情监控源事件计数接口。"""

import json

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.alerts.models.alert_source import AlertSource
from apps.alerts.service.push_source_counts import MemoryHashStore, PushSourceCountCache
from apps.alerts.views.alert_source import AlertSourceModelViewSet


@pytest.fixture
def superuser(authenticated_user):
    authenticated_user.is_superuser = True
    return authenticated_user


@pytest.fixture(autouse=True)
def memory_counts(monkeypatch):
    from apps.alerts.service import push_source_counts as counts_mod

    cache = PushSourceCountCache(store=MemoryHashStore())
    monkeypatch.setattr(counts_mod, "_default_counts", cache)
    return cache


def _request(path, user, team=None):
    factory = APIRequestFactory()
    request = factory.get(path)
    force_authenticate(request, user=user)
    if team is not None:
        request.COOKIES["current_team"] = str(team)
    return request


def _items(response):
    if hasattr(response, "render"):
        response.render()
        payload = json.loads(response.rendered_content)
    else:
        payload = json.loads(response.content)
    data = payload["data"]
    return data["items"] if isinstance(data, dict) else data


@pytest.mark.django_db
def test_push_source_stats_returns_cached_counts_for_source(superuser, memory_counts):
    source = AlertSource.objects.create(name="K8s", source_id="k8s", source_type="restful", secret="s")
    AlertSource.objects.create(name="NATS", source_id="nats", source_type="nats", secret="s")
    memory_counts.observe_events(
        [
            type("E", (), {"source": type("S", (), {"source_id": "k8s"})(), "push_source_id": "cluster-a", "team": [1]})(),
            type("E", (), {"source": type("S", (), {"source_id": "k8s"})(), "push_source_id": "cluster-a", "team": [1]})(),
            type("E", (), {"source": type("S", (), {"source_id": "nats"})(), "push_source_id": "lite-monitor", "team": [1]})(),
        ]
    )
    memory_counts.store.set(memory_counts.ready_key(1, "k8s"), 1)
    memory_counts.store.set(memory_counts.ready_key(1, "nats"), 1)
    request = _request(f"/alert_source/{source.id}/push_source_stats/", superuser, team=1)
    response = AlertSourceModelViewSet.as_view({"get": "push_source_stats"})(request, pk=str(source.id))
    assert response.status_code == status.HTTP_200_OK
    assert _items(response) == [{"id": "cluster-a", "count": 2}]
