"""事故协作列表回复查询次数。

列表已 prefetch replies 时，序列化不得再按条 order_by、exists 或 count。
10 条和 100 条顶层更新的 parent_id 查询数必须相同。
"""

import json
from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.alerts.models.models import Incident, IncidentUpdate
from apps.alerts.serializers.incident_update import IncidentUpdateSerializer
from apps.alerts.views.incident_update import IncidentUpdateViewSet


@pytest.fixture
def superuser(authenticated_user):
    authenticated_user.is_superuser = True
    return authenticated_user


@pytest.fixture(autouse=True)
def _grant(monkeypatch):
    monkeypatch.setattr(
        "apps.core.utils.viewset_utils.get_permission_rules",
        lambda *args, **kwargs: {"instance": [], "team": ["1"]},
    )


def _request(method, path, user, data=None, team="1"):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    request = fn(path) if data is None else fn(path, data=data, format="json")
    request.COOKIES["current_team"] = team
    force_authenticate(request, user=user)
    return request


def _render(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


def _make_incident(incident_id, operator=None):
    return Incident.objects.create(
        incident_id=incident_id,
        level="0",
        title="t",
        fingerprint=incident_id,
        team=[1],
        operator=operator or ["testuser"],
    )


def _normalized_sql(sql):
    return sql.lower().replace('"', "").replace("`", "").replace("[", "").replace("]", "")


def _parent_id_query_count(captured):
    count = 0
    for query in captured.captured_queries:
        sql = _normalized_sql(query["sql"])
        if "alerts_incident_update" in sql and "parent_id" in sql:
            count += 1
    return count


def _list_items(user, incident):
    request = _request(
        "get",
        f"/api/v1/alerts/api/incident/{incident.id}/updates/?page=1&page_size=100",
        user,
    )
    with CaptureQueriesContext(connection) as captured:
        response = IncidentUpdateViewSet.as_view({"get": "list"})(request, incident_pk=str(incident.id))
        payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    data = payload["data"]
    items = data["items"] if isinstance(data, dict) else data
    return items, _parent_id_query_count(captured)


def _seed_parents_with_one_reply(incident, count):
    parents = IncidentUpdate.objects.bulk_create(
        [
            IncidentUpdate(
                incident=incident,
                author="testuser",
                update_type="progress",
                content=f"parent-{index}",
            )
            for index in range(count)
        ]
    )
    IncidentUpdate.objects.bulk_create(
        [
            IncidentUpdate(
                incident=incident,
                parent=parent,
                author="testuser",
                update_type="progress",
                content=f"reply-{parent.id}",
            )
            for parent in parents
        ]
    )


@pytest.mark.django_db
def test_list_reply_query_count_stays_flat_for_10_and_100(superuser):
    incident_10 = _make_incident("reply-query-10")
    incident_100 = _make_incident("reply-query-100")
    _seed_parents_with_one_reply(incident_10, 10)
    _seed_parents_with_one_reply(incident_100, 100)

    items_10, queries_10 = _list_items(superuser, incident_10)
    items_100, queries_100 = _list_items(superuser, incident_100)

    assert len(items_10) == 10
    assert len(items_100) == 100
    assert all(item["reply_count"] == 1 and len(item["replies"]) == 1 for item in items_10)
    assert all(item["reply_count"] == 1 and len(item["replies"]) == 1 for item in items_100)
    assert (queries_10, queries_100) == (3, 3)


@pytest.mark.django_db
def test_list_replies_keep_created_at_order_count_and_empty_list(superuser):
    from apps.system_mgmt.models.user import User as SysUser

    SysUser.objects.create(username="testuser", display_name="测试用户", domain="domain.com")
    incident = _make_incident("reply-order")
    parent = IncidentUpdate.objects.create(
        incident=incident, author="testuser", update_type="progress", content="with-replies"
    )
    empty = IncidentUpdate.objects.create(
        incident=incident, author="testuser", update_type="progress", content="without-replies"
    )
    later = IncidentUpdate.objects.create(
        incident=incident, parent=parent, author="testuser", update_type="progress", content="later"
    )
    earlier = IncidentUpdate.objects.create(
        incident=incident, parent=parent, author="testuser", update_type="progress", content="earlier"
    )
    base = timezone.now()
    IncidentUpdate.objects.filter(pk=later.pk).update(created_at=base - timedelta(minutes=2))
    IncidentUpdate.objects.filter(pk=earlier.pk).update(created_at=base - timedelta(minutes=1))

    items, _queries = _list_items(superuser, incident)
    by_content = {item["content"]: item for item in items}

    ordered = by_content["with-replies"]
    assert ordered["reply_count"] == 2
    assert [reply["content"] for reply in ordered["replies"]] == ["later", "earlier"]
    assert [reply["created_at"] for reply in ordered["replies"]] == sorted(
        reply["created_at"] for reply in ordered["replies"]
    )
    assert ordered["author_display_name"] == "测试用户"
    assert ordered["replies"][0]["author_display_name"] == "测试用户"

    assert by_content["without-replies"]["replies"] == []
    assert by_content["without-replies"]["reply_count"] == 0
    assert empty.content == "without-replies"


@pytest.mark.django_db
def test_unprefetched_create_response_orders_replies_with_one_query(superuser):
    incident = _make_incident("reply-create", operator=["testuser"])
    parent = IncidentUpdate.objects.create(
        incident=incident, author="testuser", update_type="progress", content="parent"
    )
    later = IncidentUpdate.objects.create(
        incident=incident, parent=parent, author="testuser", update_type="progress", content="later"
    )
    earlier = IncidentUpdate.objects.create(
        incident=incident, parent=parent, author="testuser", update_type="progress", content="earlier"
    )
    base = timezone.now()
    IncidentUpdate.objects.filter(pk=later.pk).update(created_at=base - timedelta(minutes=2))
    IncidentUpdate.objects.filter(pk=earlier.pk).update(created_at=base - timedelta(minutes=1))

    request = _request(
        "post",
        f"/api/v1/alerts/api/incident/{incident.id}/updates/",
        superuser,
        data={"update_type": "progress", "content": "newest", "parent": parent.id},
    )
    response = IncidentUpdateViewSet.as_view({"post": "create"})(request, incident_pk=str(incident.id))
    created = _render(response)
    assert response.status_code == status.HTTP_201_CREATED
    assert created["data"]["content"] == "newest"
    assert created["data"]["replies"] == []
    assert created["data"]["reply_count"] == 0

    fresh = IncidentUpdate.objects.get(pk=parent.pk)
    assert "replies" not in getattr(fresh, "_prefetched_objects_cache", {})
    with CaptureQueriesContext(connection) as captured:
        data = IncidentUpdateSerializer(fresh, context={"request": request}).data

    assert [reply["content"] for reply in data["replies"]] == ["later", "earlier", "newest"]
    assert data["reply_count"] == 3
    assert [reply["created_at"] for reply in data["replies"]] == sorted(reply["created_at"] for reply in data["replies"])
    assert _parent_id_query_count(captured) == 1
