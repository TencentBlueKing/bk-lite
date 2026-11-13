"""关注、标签与关联的对象权限和闭环行为。"""
import json
from unittest.mock import patch

import pytest

from apps.itsm.models import TicketFollower, TicketLog, TicketRelation, TicketTag
from apps.itsm.services.ticket.service import TicketService
from apps.itsm.tests import test_review_regressions as review
from apps.itsm.tests.test_review_regressions import request
from apps.itsm.views.m2 import followers, relations, ticket_tags
from apps.itsm.views.tickets import tickets

pytestmark = pytest.mark.django_db


@pytest.fixture
def sample():
    return review.sample.__wrapped__()


def data(response):
    assert response.status_code == 200, response.content
    return json.loads(response.content)["data"]


@pytest.mark.parametrize("view", [ticket_tags, relations])
def test_view_permission_can_read_but_not_write(sample, view):
    ticket, _ = sample
    assert view(request(username="owner", permissions=["ticket-View"]), ticket.id).status_code == 200
    assert view(request("post", {}, "owner", ["ticket-View"]), ticket.id).status_code == 403
    assert view(request("delete", {}, "owner", ["ticket-View"]), ticket.id).status_code == 403
    assert view(request(username="outsider"), ticket.id).status_code == 404


def test_follow_is_idempotent_and_filters_my_list(sample):
    ticket, _ = sample
    for _ in range(2):
        assert data(followers(request("post", {"following": True}, "owner"), ticket.id))["following"]
    assert ticket.followers.count() == 1
    assert data(tickets(request(payload={"tab": "following"}, username="owner")))["count"] == 1
    assert data(tickets(request(payload={"tab": "following"}, username="handler")))["count"] == 0
    assert not data(followers(request("post", {"following": False}, "owner"), ticket.id))["following"]
    assert data(tickets(request(payload={"tab": "following"}, username="owner")))["count"] == 0


def test_tags_remove_only_current_ticket_binding(sample):
    ticket, _ = sample
    other = TicketService().create(ticket.workflow_version, {"title": "另一个", "amount": 1}, "owner")
    tag_id = data(ticket_tags(request("post", {"name": " 数据库 "}, "owner"), ticket.id))["id"]
    data(ticket_tags(request("post", {"name": "数据库"}, "owner"), other.id))
    data(ticket_tags(request("delete", {"id": tag_id}, "owner"), ticket.id))
    assert not ticket.tags.exists()
    assert other.tags.filter(id=tag_id).exists()
    assert TicketTag.objects.filter(id=tag_id).exists()


@pytest.mark.parametrize("name", ["", " ", "x" * 65, ["bad"]])
def test_invalid_tags_rejected(sample, name):
    assert ticket_tags(request("post", {"name": name}, "owner"), sample[0].id).status_code == 400


def test_relations_bidirectional_deduplicate_and_remove(sample):
    ticket, _ = sample
    other = TicketService().create(ticket.workflow_version, {"title": "关联对象", "amount": 1}, "owner")
    relation = data(relations(request("post", {"related_id": other.id}, "owner"), ticket.id))
    assert relations(request("post", {"related_id": ticket.id}, "owner"), other.id).status_code == 400
    reverse = data(relations(request(username="owner"), other.id))["items"]
    assert reverse[0]["related_id"] == ticket.id
    assert reverse[0]["related_title"] == ticket.title
    data(relations(request("delete", {"id": relation["id"]}, "owner"), other.id))
    assert not data(relations(request(username="owner"), ticket.id))["items"]


def test_relation_scope_and_self_validation(sample):
    ticket, _ = sample
    assert relations(request("post", {"related_id": ticket.id}, "owner"), ticket.id).status_code == 400
    other = TicketService().create(ticket.workflow_version, {"title": "私有", "amount": 1}, "outsider")
    assert relations(request("post", {"related_id": other.id}, "owner"), ticket.id).status_code == 404
    rel = TicketRelation.objects.create(ticket=ticket, related=other)
    assert data(relations(request(username="owner"), ticket.id))["items"] == []
    assert relations(request("delete", {"id": rel.id}, "owner"), ticket.id).status_code == 404
    other.domain = "other.com"
    other.save()
    assert relations(request("post", {"related_id": other.id}, "owner"), ticket.id).status_code == 404


def test_child_relation_cannot_be_removed(sample):
    ticket, _ = sample
    other = TicketService().create(ticket.workflow_version, {"title": "子单", "amount": 1}, "owner")
    rel = TicketRelation.objects.create(ticket=ticket, related=other, relation_type="child")
    assert relations(request("delete", {"id": rel.id}, "owner"), ticket.id).status_code == 400
    assert TicketRelation.objects.filter(pk=rel.pk).exists()


def test_follower_notification_after_commit_and_unfollow(sample, django_capture_on_commit_callbacks):
    ticket, _ = sample
    TicketFollower.objects.create(ticket=ticket, username="owner")
    with patch("apps.itsm.signals.deliver_with_retry") as notify:
        with django_capture_on_commit_callbacks(execute=True):
            TicketLog.objects.create(ticket=ticket, action="approve", operator="handler")
            assert not notify.called
        assert notify.call_count == 1
        assert notify.call_args.args[2] == ["owner"]
        notify.reset_mock()
        ticket.followers.all().delete()
        with django_capture_on_commit_callbacks(execute=True):
            TicketLog.objects.create(ticket=ticket, action="reject", operator="handler")
        assert not notify.called


def test_search_excludes_self_related_and_invisible(sample):
    ticket, _ = sample
    related = TicketService().create(ticket.workflow_version, {"title": "搜索候选", "amount": 1}, "owner")
    available = TicketService().create(ticket.workflow_version, {"title": "搜索候选", "amount": 1}, "owner")
    TicketService().create(ticket.workflow_version, {"title": "搜索候选", "amount": 1}, "outsider")
    TicketRelation.objects.create(ticket=related, related=ticket)
    result = data(tickets(request(payload={"q": "搜索候选", "relation_for": ticket.id}, username="owner")))
    assert [row["id"] for row in result["items"]] == [available.id]


def test_comment_notice_excludes_actor_and_rollback(sample, django_capture_on_commit_callbacks):
    from django.db import transaction

    from apps.itsm.models import TicketComment

    ticket, _ = sample
    TicketFollower.objects.create(ticket=ticket, username="owner")
    TicketFollower.objects.create(ticket=ticket, username="handler")
    with patch("apps.itsm.signals.deliver_with_retry") as notify:
        with django_capture_on_commit_callbacks(execute=True):
            TicketComment.objects.create(ticket=ticket, content="内容", created_by="handler")
        assert notify.call_args.args[2] == ["owner"]
        assert notify.call_args.args[1]["url"] == f"/itsm/tickets/{ticket.id}"
        notify.reset_mock()
        with django_capture_on_commit_callbacks(execute=True):
            with pytest.raises(ValueError), transaction.atomic():
                TicketLog.objects.create(ticket=ticket, action="approve", operator="handler")
                raise ValueError("回滚")
        notify.assert_not_called()


def test_follow_keeps_visibility_without_granting_other_ticket_access(sample):
    from apps.itsm.views.tickets import ticket_detail

    ticket, task = sample
    data(followers(request("post", {"following": True}, "handler"), ticket.id))
    task.assignee = "another"
    task.save()
    assert ticket_detail(request(username="handler", permissions=["ticket-View"]), ticket.id).status_code == 200
    assert followers(request("post", {"following": True}, "outsider"), ticket.id).status_code == 404


def test_legacy_reverse_duplicates_are_one_relation_and_removed_together(sample):
    ticket, _ = sample
    other = TicketService().create(ticket.workflow_version, {"title": "历史重复关联", "amount": 1}, "owner")
    first = TicketRelation.objects.create(ticket=ticket, related=other)
    TicketRelation.objects.create(ticket=other, related=ticket)
    assert len(data(relations(request(username="owner"), ticket.id))["items"]) == 1
    data(relations(request("delete", {"id": first.id}, "owner"), ticket.id))
    assert not TicketRelation.objects.filter(ticket__in=[ticket, other], related__in=[ticket, other]).exists()


def test_tag_color_roundtrip_and_validation(sample):
    ticket, _ = sample
    result = data(ticket_tags(request("post", {"name": "重点", "color": "#722ed1"}, "owner"), ticket.id))
    assert result["color"] == "#722ed1"
    assert data(ticket_tags(request(username="owner"), ticket.id))["items"][0]["color"] == "#722ed1"
    assert ticket_tags(request("post", {"name": "错误", "color": "javascript:bad"}, "owner"), ticket.id).status_code == 400
    result = data(ticket_tags(request("post", {"name": "重点", "color": "#1677ff"}, "owner"), ticket.id))
    assert result["color"] == "#722ed1"
