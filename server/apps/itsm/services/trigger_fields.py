import math
import re
from collections import defaultdict
from itertools import islice
from operator import attrgetter

from django.db.models import F

from apps.itsm.models import FormModel, Service, Workflow
from apps.itsm.services.form.options import resolve_options


def _ticket_status(ticket):
    return ticket.status.key if ticket.status_id else ""


SYSTEM_FIELDS = {
    "sn": ("工单编号", "text", attrgetter("sn")),
    "title": ("工单标题", "text", attrgetter("title")),
    "status": ("工单状态", "text", _ticket_status),
    "creator": ("提单人", "text", attrgetter("creator")),
    "workflow_id": ("流程", "number", attrgetter("workflow_id")),
    "service_id": ("服务", "number", attrgetter("service_id")),
    "is_test": ("是否测试单", "boolean", attrgetter("is_test")),
}
TEXT_FIELDS = {"input", "textarea", "richtext", "radio", "select", "date", "datetime", "time", "cascade"}
LIST_FIELDS = {"checkbox", "multiselect", "multiCascade", "multiUser", "multiUserGroup", "dateRange"}
NUMERIC_FIELDS = {"number", "calculate"}
FIELD_TYPES = {
    **dict.fromkeys(TEXT_FIELDS, "text"),
    **dict.fromkeys(LIST_FIELDS, "list"),
    **dict.fromkeys(NUMERIC_FIELDS, "number"),
}
CHOICE_FIELDS = {"radio", "select", "cascade", "checkbox", "multiselect", "multiCascade"}
PERSON_FIELDS = {"user", "multiUser"}


def trigger_condition_values(ticket):
    data = ticket.form_data or {}
    system = {key: get_value(ticket) for key, (_, _, get_value) in SYSTEM_FIELDS.items()}
    return {**data, "status": system["status"], "$ticket": system, "$form": data}


def trigger_option_catalog(domain, user):
    from apps.itsm.services.trigger_config import status_options
    from apps.itsm.services.trigger_notice import notice_options

    workflows = list(Workflow.objects.filter(domain=domain).order_by("name", "id").values("id", "name"))
    forms = _forms(domain)
    services, service_ids = _services(domain)
    schemas = _form_schema_groups(domain, forms, service_ids)
    action_statuses, condition_statuses = status_options(domain)
    choices = {
        "status": _options(condition_statuses, "key"),
        "workflow_id": _options(workflows),
        "service_id": _options(services),
        "is_test": [{"label": "是", "value": True}, {"label": "否", "value": False}],
    }
    return {
        "workflows": workflows,
        "forms": forms,
        "services": services,
        "statuses": action_statuses,
        "system_fields": [
            {"key": f"$ticket.{key}", "label": label, "type": kind, **({"options": choices[key]} if key in choices else {})}
            for key, (label, kind, _) in SYSTEM_FIELDS.items()
        ],
        "form_field_groups": _catalog_fields(schemas, _form_fields),
        "notice": notice_options(domain, user, _catalog_fields(schemas, person_form_fields)),
    }


def _options(rows, key="id"):
    return [{"label": row["name"], "value": row[key]} for row in rows]


def _forms(domain):
    return list(FormModel.objects.filter(domain=domain).order_by("name", "id").values("id", "name"))


def _services(domain):
    services, service_ids = [], defaultdict(list)
    for row in Service.objects.filter(domain=domain).order_by("name", "id").values("id", "name", "workflow_id"):
        services.append({"id": row["id"], "name": row["name"]})
        service_ids[row["workflow_id"]].append(row["id"])
    return services, service_ids


def _form_schema_groups(domain, forms, service_ids):
    form_schemas = dict(
        FormModel.objects.filter(
            domain=domain, current_version__domain=domain, current_version__is_published=True, current_version__form_id=F("id")
        ).values_list("id", "current_version__schema")
    )
    workflows = (
        Workflow.objects.filter(
            domain=domain, current_version__domain=domain, current_version__is_published=True, current_version__workflow_id=F("id")
        )
        .order_by("name", "id")
        .values("id", "name", "form_id", "current_version__design")
    )
    form_ids = {form["id"] for form in forms}
    groups = []
    for workflow in workflows:
        design = workflow["current_version__design"]
        if not isinstance(design, dict):
            design = {}
        schema = design.get("form_schema")
        if not isinstance(schema, dict):
            schema = form_schemas.get(workflow["form_id"])
        group = {"name": workflow["name"], "workflow_id": workflow["id"], "service_ids": service_ids[workflow["id"]]}
        form_id = design.get("form_model_id", workflow["form_id"])
        if type(form_id) is int and form_id in form_ids:
            group["form_id"] = form_id
        groups.append((group, schema))
    for form in forms:
        groups.append(({"name": form["name"], "form_id": form["id"]}, form_schemas.get(form["id"])))
    return groups


def _catalog_fields(schemas, reader):
    return [{**group, "fields": fields} for group, schema in schemas if (fields := reader(schema))]


def person_field_catalog(domain):
    _, service_ids = _services(domain)
    return _catalog_fields(_form_schema_groups(domain, _forms(domain), service_ids), person_form_fields)


def _schema_fields(schema):
    if not isinstance(schema, dict):
        return

    def walk(entries):
        for field in _records(entries):
            key, kind = field.get("key"), field.get("type")
            if not isinstance(key, str) or not isinstance(kind, str) or not re.fullmatch(r"[^.\s]+", key) or field.get("state") == "hidden":
                continue
            if kind in {"section", "tab"}:
                yield from walk(field.get("children"))
            else:
                label = field.get("label")
                yield key, kind, label.strip() if isinstance(label, str) and label.strip() else key, field

    yield from walk(schema.get("fields"))


def _form_fields(schema):
    fields = {}
    for key, kind, label, field in _schema_fields(schema):
        if kind not in FIELD_TYPES or key in fields:
            continue
        item = {"key": f"$form.{key}", "label": label, "type": FIELD_TYPES[kind]}
        if kind in CHOICE_FIELDS and (field.get("fetch") or {}).get("mode") != "options":
            choices = list(islice(_field_choices(resolve_options(field)), 500))
            if choices:
                item["options"] = choices
        fields[key] = item
    return list(fields.values())


def person_form_fields(schema):
    fields = {}
    for key, kind, label, _ in _schema_fields(schema):
        if kind in PERSON_FIELDS:
            fields.setdefault(key, {"key": key, "label": label})
    return list(fields.values())


def _records(value):
    return (item for item in value if isinstance(item, dict)) if isinstance(value, list) else ()


def _field_choices(options):
    for option in _records(options):
        value = option.get("value")
        if type(value) in {str, bool, int} or (type(value) is float and math.isfinite(value)):
            label = option.get("label")
            yield {"label": label if isinstance(label, str) and label.strip() else str(value), "value": value}
        yield from _field_choices(option.get("children"))
