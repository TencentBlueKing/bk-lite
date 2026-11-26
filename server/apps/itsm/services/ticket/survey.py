import re
from operator import attrgetter

from apps.itsm.models import SurveyTemplate, TicketLog

SURVEY_READY = "survey_ready"
MAX_QUESTIONS = 20
MAX_ANSWER_LENGTH = 1000


class SurveyValidationError(ValueError):
    pass


def _questions(value):
    if not isinstance(value, list) or len(value) > MAX_QUESTIONS:
        raise SurveyValidationError(f"满意度模板最多包含 {MAX_QUESTIONS} 道题")
    questions = []
    identifiers = set()
    for question in value:
        if not isinstance(question, dict):
            raise SurveyValidationError("题目配置格式不正确")
        identifier = question.get("id")
        title = question.get("title")
        required = question.get("required", False)
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", identifier) or identifier in identifiers:
            raise SurveyValidationError("题目标识无效或重复")
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 200 or not isinstance(required, bool):
            raise SurveyValidationError("题目内容须为 1 至 200 字，必填设置须为布尔值")
        identifiers.add(identifier)
        questions.append({"id": identifier, "title": title.strip(), "required": required})
    return questions


def normalize_survey_template(values, *, creating=False):
    normalized = {**values}
    if creating or "name" in values:
        name = values.get("name")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 128:
            raise SurveyValidationError("模板名称须为 1 至 128 字")
        normalized["name"] = name.strip()
    if "questions" in values:
        normalized["questions"] = _questions(values["questions"])
    return normalized


def record_survey_invitation(ticket, operator):
    if hasattr(ticket, "survey"):
        return
    template = SurveyTemplate.objects.filter(domain=ticket.domain).order_by("-id").first()
    if template is None:
        return
    try:
        questions = _questions(template.questions)
    except SurveyValidationError:
        questions = []
    TicketLog.objects.create(
        ticket=ticket,
        domain=ticket.domain,
        action=SURVEY_READY,
        operator=operator,
        message="请填写满意度",
        detail={"survey_template": {"name": template.name, "questions": questions}},
        created_by=operator,
        updated_by=operator,
    )


def survey_snapshot(ticket, logs):
    if ticket.finished_at is None:
        return None
    invitation = max(
        (log for log in logs if log.action == SURVEY_READY and log.created_at >= ticket.finished_at),
        key=attrgetter("id"),
        default=None,
    )
    return (invitation.detail or {}).get("survey_template") if invitation else None


def survey_data(survey):
    return {"score": survey.score, "comment": survey.comment, "answers": survey.answers}


def survey_submission(payload, template):
    if not isinstance(payload, dict):
        raise SurveyValidationError("评价格式不正确")
    score = payload.get("score")
    if isinstance(score, str) and score in {"1", "2", "3", "4", "5"}:
        score = int(score)
    if type(score) is not int or not 1 <= score <= 5:
        raise SurveyValidationError("评分应为 1 到 5")
    comment = payload.get("comment", "")
    if not isinstance(comment, str) or len(comment.strip()) > 500:
        raise SurveyValidationError("评价意见不能超过 500 字")
    answers = payload.get("answers", {})
    questions = template["questions"] if template else []
    if not isinstance(answers, dict) or answers.keys() - {question["id"] for question in questions}:
        raise SurveyValidationError("问卷答案包含未知题目")

    responses = []
    for question in questions:
        value = answers.get(question["id"], "")
        if not isinstance(value, str) or len(value.strip()) > MAX_ANSWER_LENGTH:
            raise SurveyValidationError(f"答复不能超过 {MAX_ANSWER_LENGTH} 字")
        value = value.strip()
        if not value and question["required"]:
            raise SurveyValidationError(f"请回答「{question['title']}」")
        if value:
            responses.append({"id": question["id"], "title": question["title"], "value": value})
    return {"score": score, "comment": comment.strip(), "answers": responses}
