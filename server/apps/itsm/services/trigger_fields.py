import math
import re
from collections import defaultdict
from itertools import islice
from operator import attrgetter

from django.db.models import Case, F, JSONField, Q, When

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


def _form_schema_groups(domain, forms, service_ids, *, workflow_ids=None):
    workflows = Workflow.objects.filter(
        domain=domain, current_version__domain=domain, current_version__is_published=True, current_version__workflow_id=F("id")
    ).order_by("name", "id")
    if workflow_ids is not None:
        workflows = workflows.filter(pk__in=workflow_ids)
    workflow_rows = list(
        workflows.annotate(
            snapshot=F("current_version__design__form_schema"),
            snapshot_form_id=F("current_version__design__form_model_id"),
            snapshot_has_form=Case(When(current_version__design__has_key="form_model_id", then=True), default=False),
        ).values("id", "name", "form_id", "snapshot", "snapshot_form_id", "snapshot_has_form")
    )
    form_ids = {form["id"] for form in forms}
    for workflow in workflow_rows:
        if type(workflow["snapshot_form_id"]) is int:
            form_ids.add(workflow["snapshot_form_id"])
        if workflow["form_id"] is not None:
            form_ids.add(workflow["form_id"])
    form_schemas = dict(
        FormModel.objects.filter(domain=domain, pk__in=form_ids)
        .annotate(
            schema=Case(
                When(
                    current_version__domain=domain,
                    current_version__is_published=True,
                    current_version__form_id=F("id"),
                    then=F("current_version__schema"),
                ),
                output_field=JSONField(),
            )
        )
        .values_list("id", "schema")
    )
    groups = []
    for workflow in workflow_rows:
        schema = workflow["snapshot"]
        if not isinstance(schema, dict):
            schema = form_schemas.get(workflow["form_id"])
        group = {"name": workflow["name"], "workflow_id": workflow["id"], "service_ids": service_ids[workflow["id"]]}
        form_id = workflow["snapshot_form_id"] if workflow["snapshot_has_form"] else workflow["form_id"]
        if type(form_id) is int and form_id in form_schemas:
            group["form_id"] = form_id
        groups.append((group, schema))
    for form in forms:
        groups.append(({"name": form["name"], "form_id": form["id"]}, form_schemas.get(form["id"])))
    return groups


def _catalog_fields(schemas, reader):
    return [{**group, "fields": fields} for group, schema in schemas if (fields := reader(schema))]


def scoped_person_field_keys(domain, scope, requested):
    if not requested:
        return set()
    forms = FormModel.objects.filter(domain=domain, current_version__domain=domain, current_version__is_published=True, current_version__form_id=F("pk"))
    workflows = Workflow.objects.filter(domain=domain, current_version__domain=domain, current_version__is_published=True, current_version__workflow_id=F("pk"))
    match = Q()
    if "workflow_ids" in scope:
        match &= Q(pk__in=scope["workflow_ids"])
    if "form_ids" in scope:
        match &= Q(current_version__design__form_model_id__in=scope["form_ids"]) | (
            ~Q(current_version__design__has_key="form_model_id") & Q(form_id__in=scope["form_ids"])
        )
    if scope["mode"] == "include":
        if "service_ids" in scope:
            match &= Q(pk__in=Service.objects.filter(domain=domain, pk__in=scope["service_ids"]).values("workflow_id"))
        workflows = workflows.filter(match)
        if "workflow_ids" in scope or "service_ids" in scope:
            forms = forms.none()
        elif "form_ids" in scope:
            forms = forms.filter(pk__in=scope["form_ids"])
    elif scope["mode"] == "exclude" and "service_ids" not in scope:
        workflows = workflows.exclude(match)
        if "form_ids" in scope and "workflow_ids" not in scope:
            forms = forms.exclude(pk__in=scope["form_ids"])
    fallback = Case(
        When(form__domain=domain, form__current_version__domain=domain, form__current_version__form_id=F("form_id"),
             form__current_version__is_published=True, then=F("form__current_version__schema")), output_field=JSONField(),
    )
    found = set()
    for snapshot, published_form in workflows.values_list("current_version__design__form_schema", fallback).iterator(chunk_size=50):
        schema = snapshot if isinstance(snapshot, dict) else published_form
        found.update(key for key, kind, _, _ in _schema_fields(schema) if kind in PERSON_FIELDS and key in requested)
        if found == requested:
            return found
    for schema in forms.values_list("current_version__schema", flat=True).iterator(chunk_size=50):
        found.update(key for key, kind, _, _ in _schema_fields(schema) if kind in PERSON_FIELDS and key in requested)
        if found == requested:
            break
    return found


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
