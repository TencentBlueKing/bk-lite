import json

import pytest

from apps.itsm.models import SurveyTemplate, TicketSurvey
from apps.itsm.services.ticket.service import TicketService
from apps.itsm.tests import test_review_regressions
from apps.itsm.tests.test_review_regressions import request
from apps.itsm.views.extend import resource_item, resources
from apps.itsm.views.tickets import ticket_detail, ticket_survey

pytestmark = pytest.mark.django_db
sample = test_review_regressions.sample


def data(response):
    assert response.status_code == 200, response.content
    return json.loads(response.content)["data"]


def test_latest_local_template_is_preserved_when_ticket_finishes(sample):
    ticket, _task = sample
    SurveyTemplate.objects.create(name="旧版", domain=ticket.domain)
    questions = [{"id": "service", "title": "解决结果是否符合预期", "required": True}]
    template = SurveyTemplate.objects.create(name="服务反馈", domain=ticket.domain, questions=questions)
    SurveyTemplate.objects.create(name="其他租户的新模板", domain="foreign.example")

    TicketService().finish_if_ended(ticket)
    detail = data(ticket_detail(request(username="owner"), ticket.id))
    assert detail["can_survey"]
    assert detail["survey_template"] == {"name": "服务反馈", "questions": questions}

    template.delete()
    assert data(ticket_detail(request(username="owner"), ticket.id))["survey_template"]["questions"] == questions
    assert ticket_survey(request("post", {"score": 5}, "owner"), ticket.id).status_code == 400
    assert ticket_survey(request("post", {"score": 5, "answers": {"service": "已恢复", "extra": "未知题目"}}, "owner"), ticket.id).status_code == 400
    assert not TicketSurvey.objects.filter(ticket=ticket).exists()

    submission = {"score": 5, "comment": "谢谢", "answers": {"service": " 已恢复 "}}
    result = data(ticket_survey(request("post", submission, "owner"), ticket.id))
    assert result["answers"] == [{"id": "service", "title": "解决结果是否符合预期", "value": "已恢复"}]
    assert data(ticket_survey(request("post", submission, "owner"), ticket.id)) == result
    submission["score"] = 1
    assert ticket_survey(request("post", submission, "owner"), ticket.id).status_code == 409
    completed = data(ticket_detail(request(username="owner"), ticket.id))
    assert not completed["can_survey"]
    assert completed["survey"] == result


def test_other_domain_template_does_not_affect_existing_score_and_comment(sample):
    ticket, _task = sample
    SurveyTemplate.objects.create(name="其他租户", domain="foreign.example")
    TicketService().finish_if_ended(ticket)

    assert not ticket.logs.filter(action="survey_ready").exists()
    assert data(ticket_detail(request(username="owner"), ticket.id))["survey_template"] is None
    assert ticket_survey(request("post", {"score": 5}, "handler"), ticket.id).status_code == 403
    assert ticket_survey(request("post", {"score": 5}, "owner", domain="foreign.example"), ticket.id).status_code == 404
    assert data(ticket_survey(request("post", {"score": 4, "comment": "旧表单"}, "owner"), ticket.id)) == {
        "score": 4,
        "comment": "旧表单",
        "answers": [],
    }


def test_template_api_enforces_questions_and_permissions():
    permissions = ["survey-View", "survey-Add", "survey-Edit", "survey-Delete"]
    questions = [{"id": "service", "title": " 处理结果 ", "required": True}]
    response = resources(request("post", {"name": " 服务反馈 ", "questions": questions}, "admin", permissions), "surveys")
    item = data(response)
    assert item["name"] == "服务反馈"
    assert item["questions"] == [{"id": "service", "title": "处理结果", "required": True}]

    readonly = data(resources(request(username="viewer", permissions=["survey-View"]), "surveys"))
    assert not readonly["can_add"] and not readonly["can_edit"] and not readonly["can_delete"]
    assert resource_item(request("put", {"name": "无权修改"}, "viewer", ["survey-View"]), "surveys", item["id"]).status_code == 403
    assert resource_item(request("put", {"questions": questions * 2}, "admin", permissions), "surveys", item["id"]).status_code == 400
    assert (
        resource_item(
            request("put", {"questions": [{"id": "service", "title": "新问题", "required": "false"}]}, "admin", permissions),
            "surveys",
            item["id"],
        ).status_code
        == 400
    )
    assert data(
        resource_item(
            request("put", {"questions": [{"id": "service", "title": "修订问题", "required": False}]}, "admin", permissions),
            "surveys",
            item["id"],
        )
    )["questions"] == [{"id": "service", "title": "修订问题", "required": False}]
