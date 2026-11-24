import re

from django.db.models import Case, OuterRef, Q, Subquery, When
from pydantic import ValidationError

from apps.core.models.maintainer_info import DEFAULT_MAINTAINER_DOMAIN
from apps.itsm.models import FormModel, Service, TicketStatus, Workflow
from apps.itsm.services.trigger_notice import NoticeConfigError, TriggerNotice, validate_notice_references

EVENT_ALIASES = {
    "create": "ticket_create",
    "save": "ticket_update",
    "suspend": "ticket_suspend",
    "resume": "ticket_recovery",
    "return": "ticket_back",
    "withdraw": "ticket_withdraw",
    "end": "ticket_end",
    "finish": "ticket_finish",
    "close": "ticket_close",
    "terminate": "ticket_terminate",
    "urge": "ticket_urging",
    "reopen": "ticket_reopen",
    "task_enter": "activity_into",
}
EVENTS = {*EVENT_ALIASES.values(), "submit", "approve", "reject", "claim", "transfer", "respond"}
ACTION_LIMITS = {"tag": 64, "notice": 2000, "status": 32}
OPERATORS = {"=", "!=", ">", ">=", "<", "<=", "in", "not_in", "contains", "is_empty", "not_empty"}
EMPTY_OPERATORS = {"is_empty", "not_empty"}
SCOPE_MODELS = {"workflow_ids": Workflow, "form_ids": FormModel, "service_ids": Service}
ENGINE_STATUSES = {"finished", "terminated", "cancelled", "suspended"}


class TriggerConfigError(ValueError):
    pass


def normalize_condition(when, *, depth=0):
    if depth == 0 and (when is None or when == {}):
        return None
    if not isinstance(when, dict) or depth > 12:
        raise TriggerConfigError("触发条件格式错误或嵌套过深")
    if "logic" in when:
        logic, items = when["logic"], when.get("items")
        if logic not in ("and", "or") or not isinstance(items, list) or not items:
            raise TriggerConfigError("条件组需选择全部或任一，并至少包含一个条件")
        return {"logic": logic, "items": [normalize_condition(item, depth=depth + 1) for item in items]}

    field, op = when.get("field"), when.get("op")
    if depth == 0 and field == "" and op in ("eq", "=") and when.get("value") == "":
        return None
    if not isinstance(field, str) or not re.fullmatch(r"[^.\s]+(?:\.[^.\s]+)*", field.strip()):
        raise TriggerConfigError("请选择或填写有效的条件字段")
    if op == "eq":
        op = "="
    if not isinstance(op, str) or op not in OPERATORS:
        raise TriggerConfigError("触发条件运算符无效")
    item = {"field": field.strip(), "op": op}
    if op in EMPTY_OPERATORS:
        return item
    if "value" not in when:
        raise TriggerConfigError("请填写条件值")
    expected = when["value"]
    if op in {"in", "not_in"} and not isinstance(expected, list):
        raise TriggerConfigError("属于和不属于条件需要值列表")
    if op in {">", ">=", "<", "<="} and not isinstance(expected, (str, int, float)):
        raise TriggerConfigError("大小比较条件需要文本或数值")
    return {**item, "value": expected}


def normalize_scope(scope):
    if scope is None:
        return {"mode": "all"}
    if not isinstance(scope, dict) or scope.get("mode") not in ("all", "include", "exclude"):
        raise TriggerConfigError("请选择有效的触发器生效范围")
    unknown = set(scope) - {"mode", *SCOPE_MODELS}
    if unknown:
        raise TriggerConfigError("生效范围包含不支持的类型")
    mode = scope["mode"]
    result = {"mode": mode}
    if mode == "all":
        return result
    for key in SCOPE_MODELS:
        if key not in scope:
            continue
        values = scope[key]
        if not isinstance(values, list) or any(type(value) is not int or value <= 0 for value in values):
            raise TriggerConfigError("生效范围必须使用有效的流程、表单或服务")
        if values:
            result[key] = list(dict.fromkeys(values))
    if len(result) == 1:
        raise TriggerConfigError("请至少选择一个流程、表单或服务")
    return result


def scope_matches(scope, ticket):
    scope = normalize_scope(scope)
    if scope["mode"] == "all":
        return True
    matches = (
        ("workflow_ids" not in scope or ticket.workflow_id in scope["workflow_ids"])
        and ("service_ids" not in scope or ticket.service_id in scope["service_ids"])
        and ("form_ids" not in scope or _ticket_form_model_id(ticket) in scope["form_ids"])
    )
    return matches if scope["mode"] == "include" else not matches


def _ticket_form_model_id(ticket):
    if ticket.workflow_version_id and "form_model_id" in ticket.workflow_version.design:
        return ticket.workflow_version.design["form_model_id"]
    return ticket.workflow.form_id


def _status_candidates(domain):
    shared = Q(domain="") | Q(domain=DEFAULT_MAINTAINER_DOMAIN, kind=TicketStatus.Kind.BUILTIN)
    return TicketStatus.objects.filter(Q(domain=domain) | shared)


def _status_priority(row, domain):
    return 0 if row.domain == domain else 1 if not row.domain else 2


def _eligible_status(row):
    return not row.is_terminal and row.key not in ENGINE_STATUSES


def status_target(domain, key):
    row = min(_status_candidates(domain).filter(key=key), key=lambda item: _status_priority(item, domain), default=None)
    if row is None or not _eligible_status(row):
        raise TriggerConfigError("目标状态不存在或不能由触发器变更")
    return row


def status_option_queryset(domain):
    candidates = _status_candidates(domain)
    preferred = candidates.filter(key=OuterRef("key")).order_by(
        Case(When(domain=domain, then=0), When(domain="", then=1), default=2), "id"
    )
    return candidates.filter(pk=Subquery(preferred.values("pk")[:1])).order_by("order", "id")


def _normalize_actions(action, config, name):
    raw = config.get("actions")
    if "actions" not in config:
        value = config.get("response") or config.get("name")
        raw = [{"type": action, "value": value or (name if action == "notice" else "")}]
    if not isinstance(raw, list) or not raw:
        raise TriggerConfigError("请至少添加一个响应动作")
    actions = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("type"), str) or item["type"] not in ACTION_LIMITS:
            raise TriggerConfigError("请选择有效的响应动作")
        kind = item["type"]
        configured_notice = kind == "notice" and "notice" in item
        value = item.get("value", "" if configured_notice else None)
        if not isinstance(value, str) or (not configured_notice and not value.strip()) or len(value.strip()) > ACTION_LIMITS[kind]:
            raise TriggerConfigError(f"动作参数需填写 1 至 {ACTION_LIMITS[kind]} 字符")
        normalized = {"type": kind, "value": value.strip()}
        if configured_notice:
            try:
                notice = TriggerNotice.model_validate(item["notice"])
            except ValidationError as exc:
                raise TriggerConfigError("请检查通知内容方式、通知人和通知渠道，通知渠道不可重复") from exc
            if notice.content_mode == "custom":
                if not normalized["value"]:
                    raise TriggerConfigError("请填写自定义通知内容")
                if any(route.template_id is not None for route in notice.channels):
                    raise TriggerConfigError("自定义通知内容不能同时选择模板")
            elif notice.content_mode == "template" and normalized["value"]:
                raise TriggerConfigError("选择模板时不能同时填写自定义通知内容")
            normalized["notice"] = notice
        actions.append(normalized)
    return actions


def actions_for(trigger):
    if not isinstance(trigger.config, dict):
        raise TriggerConfigError("触发器配置格式错误")
    return _normalize_actions(trigger.action, trigger.config, trigger.name)


def normalize_trigger(values, *, domain, user, current=None):
    fields = {"name": "", "event": "", "action": "tag", "config": {}, "is_enabled": True}
    if current is not None:
        fields = {key: getattr(current, key) for key in fields}
    fields.update(values)
    if type(fields["is_enabled"]) is not bool:
        raise TriggerConfigError("启用状态必须为布尔值")
    name, event, config = fields["name"], fields["event"], fields["config"]
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 128:
        raise TriggerConfigError("规则名称需填写 1 至 128 字符")
    if not isinstance(event, str) or EVENT_ALIASES.get(event, event) not in EVENTS:
        raise TriggerConfigError("请选择有效的触发事件")
    if not isinstance(config, dict):
        raise TriggerConfigError("触发器配置格式错误")

    scope = normalize_scope(config.get("scope"))
    for key, model in SCOPE_MODELS.items():
        ids = scope.get(key, [])
        if ids and model.objects.filter(domain=domain, id__in=ids).count() != len(ids):
            raise TriggerConfigError("生效范围内存在无效或其他组织的项目")
    when = normalize_condition(config.get("when"))
    actions = _normalize_actions(fields["action"], config, name.strip())
    for action in actions:
        if action["type"] == "status":
            status_target(domain, action["value"])
        if "notice" in action:
            try:
                validate_notice_references(action["notice"], domain, user, scope)
            except NoticeConfigError as exc:
                raise TriggerConfigError(str(exc)) from exc
            action["notice"] = action["notice"].model_dump(exclude_none=True)
    normalized_config = {"scope": scope, "actions": actions}
    if when is not None:
        normalized_config["when"] = when
    return {
        **fields,
        "name": name.strip(),
        "event": EVENT_ALIASES.get(event, event),
        "action": actions[0]["type"],
        "config": normalized_config,
    }
