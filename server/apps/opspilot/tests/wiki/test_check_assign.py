"""WikiCheckItemViewSet.assign 检查项分配/延期/动作类型端点测试。

覆盖:
- 至少提供一个字段
- due_at 必须为 ISO 8601 时间
- 单字段/多字段更新
- 空值清除字段
- list 端点按 assignee / action_type / overdue 过滤
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.opspilot.models import CheckItem, WikiKnowledgeBase


def _kb():
    return WikiKnowledgeBase.objects.create(name="kb", team=[1])


def _check(kb, **kwargs):
    defaults = {"knowledge_base": kb, "check_type": "duplicate", "status": "open", "related": {}}
    defaults.update(kwargs)
    return CheckItem.objects.create(**defaults)


@pytest.mark.django_db
def test_assign_requires_at_least_one_field(api_client):
    kb = _kb()
    check = _check(kb)
    resp = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/check_item/{check.id}/assign/",
        {},
        format="json",
    )
    assert resp.status_code == 400
    assert resp.json()["result"] is False


@pytest.mark.django_db
def test_assign_rejects_invalid_due_at(api_client):
    kb = _kb()
    check = _check(kb)
    resp = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/check_item/{check.id}/assign/",
        {"due_at": "not-a-datetime"},
        format="json",
    )
    assert resp.status_code == 400
    assert "ISO 8601" in resp.json()["message"]


@pytest.mark.django_db
def test_assign_updates_assignee_action_type(api_client):
    kb = _kb()
    check = _check(kb)
    resp = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/check_item/{check.id}/assign/",
        {"assignee": "alice", "action_type": "review"},
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["assignee"] == "alice"
    assert body["data"]["action_type"] == "review"
    check.refresh_from_db()
    assert check.assignee == "alice"
    assert check.action_type == "review"


@pytest.mark.django_db
def test_assign_updates_due_at(api_client):
    kb = _kb()
    check = _check(kb)
    target = (timezone.now() + timedelta(days=2)).isoformat()
    resp = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/check_item/{check.id}/assign/",
        {"due_at": target},
        format="json",
    )
    assert resp.status_code == 200
    check.refresh_from_db()
    assert check.due_at is not None
    assert abs((check.due_at - timezone.now()).total_seconds() - 2 * 86400) < 5


@pytest.mark.django_db
def test_assign_clears_field_with_empty_string(api_client):
    kb = _kb()
    check = _check(kb, assignee="alice", action_type="review")
    resp = api_client.post(
        f"/api/v1/opspilot/wiki_mgmt/check_item/{check.id}/assign/",
        {"assignee": "", "action_type": ""},
        format="json",
    )
    assert resp.status_code == 200
    check.refresh_from_db()
    assert check.assignee == ""
    assert check.action_type == ""


@pytest.mark.django_db
def test_list_filters_by_assignee_unassigned_mine_and_action(api_client):
    kb = _kb()
    unassigned = _check(kb, related={"pages": []})
    mine = _check(kb, related={"pages": []}, assignee="alice")
    other = _check(kb, related={"pages": []}, assignee="bob", action_type="research")
    _check(kb, related={"pages": []}, assignee="alice", action_type="review")

    # __unassigned__
    resp = api_client.get("/api/v1/opspilot/wiki_mgmt/check_item/", {"assignee": "__unassigned__"})
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["data"]["items"]]
    assert unassigned.id in ids
    assert mine.id not in ids
    assert other.id not in ids

    # 指定用户
    resp = api_client.get("/api/v1/opspilot/wiki_mgmt/check_item/", {"assignee": "bob"})
    ids = [item["id"] for item in resp.json()["data"]["items"]]
    assert other.id in ids
    assert mine.id not in ids

    # 按 action_type
    resp = api_client.get("/api/v1/opspilot/wiki_mgmt/check_item/", {"action_type": "research"})
    ids = [item["id"] for item in resp.json()["data"]["items"]]
    assert other.id in ids
    assert mine.id not in ids

    # __mine__:登录用户是 alice(api_client fixture 默认用户)
    resp = api_client.get("/api/v1/opspilot/wiki_mgmt/check_item/", {"assignee": "__mine__"})
    assert resp.status_code == 200


@pytest.mark.django_db
def test_list_filters_overdue(api_client):
    kb = _kb()
    past = _check(kb, related={"pages": []}, due_at=timezone.now() - timedelta(hours=1))
    future = _check(kb, related={"pages": []}, due_at=timezone.now() + timedelta(hours=1))
    resp = api_client.get("/api/v1/opspilot/wiki_mgmt/check_item/", {"overdue": "1"})
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["data"]["items"]]
    assert past.id in ids
    assert future.id not in ids
