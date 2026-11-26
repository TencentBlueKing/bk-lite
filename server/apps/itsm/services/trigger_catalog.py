import json
from collections import defaultdict
from dataclasses import dataclass, field

from apps.itsm.models import FormModel, HandlerGroup, NotifyTemplate, Service, Workflow
from apps.itsm.services.notify.service import ready_im_channels
from apps.itsm.services.trigger_config import ENGINE_STATUSES, status_option_queryset
from apps.itsm.services.trigger_fields import SYSTEM_FIELDS, _catalog_fields, _form_fields, _form_schema_groups, person_form_fields
from apps.itsm.services.trigger_notice import _ready_channels

CATALOG_KEYS = {"workflows", "forms", "services", "statuses", "groups", "channels", "templates"}
MAX_PAGE_SIZE = 50


@dataclass
class CatalogPage:
    number: int
    size: int
    selected: dict
    has_more: bool = field(init=False, default=False)

    @classmethod
    def parse(cls, query):
        number = int(query.get("page", 1))
        size = int(query.get("page_size", 20))
        if not 1 <= number <= 2**31 - 1 or not 1 <= size <= MAX_PAGE_SIZE:
            raise ValueError("选项分页参数无效")
        raw = query.get("selected", "{}")
        if len(raw) > 10000:
            raise ValueError("已选项参数过长")
        selected = json.loads(raw)
        if not isinstance(selected, dict) or selected.keys() - CATALOG_KEYS:
            raise ValueError("已选项参数无效")
        for key, values in selected.items():
            if not isinstance(values, list) or len(values) > MAX_PAGE_SIZE:
                raise ValueError("已选项参数无效")
            valid = (
                (lambda value: isinstance(value, str) and 1 <= len(value) <= 32)
                if key == "statuses"
                else (lambda value: type(value) is int and 1 <= value <= 2**63 - 1)
            )
            if not all(map(valid, values)):
                raise ValueError("已选项参数无效")
        return cls(number, size, selected)

    def rows(self, kind, queryset, *, key="id"):
        offset = (self.number - 1) * self.size
        rows = list(queryset[offset : offset + self.size + 1])
        self.has_more = self.has_more or len(rows) > self.size
        rows = rows[: self.size]
        missing = set(self.selected.get(kind, [])) - {row[key] for row in rows}
        if missing:
            rows.extend(queryset.filter(**{f"{key}__in": missing}))
        return rows


def trigger_option_catalog(domain, user, page):
    workflows = page.rows("workflows", Workflow.objects.filter(domain=domain).order_by("name", "id").values("id", "name"))
    forms = page.rows("forms", FormModel.objects.filter(domain=domain).order_by("name", "id").values("id", "name"))
    service_rows = page.rows("services", Service.objects.filter(domain=domain).order_by("name", "id").values("id", "name", "workflow_id"))
    services, service_ids = [], defaultdict(list)
    for row in service_rows:
        services.append({"id": row["id"], "name": row["name"]})
        service_ids[row["workflow_id"]].append(row["id"])
    workflow_ids = {row["id"] for row in workflows} | set(service_ids)
    schemas = _form_schema_groups(domain, forms, service_ids, workflow_ids=workflow_ids)
    statuses = page.rows("statuses", status_option_queryset(domain).values("key", "name", "is_terminal"), key="key")
    choices = {
        "status": _options(statuses, "key"),
        "workflow_id": _options(workflows),
        "service_id": _options(services),
        "is_test": [{"label": "是", "value": True}, {"label": "否", "value": False}],
    }

    notice = _notice_options(domain, user, page, schemas)
    return {
        "workflows": workflows,
        "forms": forms,
        "services": services,
        "statuses": [{"key": row["key"], "name": row["name"]} for row in statuses if not row["is_terminal"] and row["key"] not in ENGINE_STATUSES],
        "system_fields": [
            {"key": f"$ticket.{key}", "label": label, "type": kind, **({"options": choices[key]} if key in choices else {})}
            for key, (label, kind, _) in SYSTEM_FIELDS.items()
        ],
        "form_field_groups": _catalog_fields(schemas, _form_fields),
        "notice": notice,
        "has_more": page.has_more,
    }


def _options(rows, key="id"):
    return [{"label": row["name"], "value": row[key]} for row in rows]


def _notice_options(domain, user, page, schemas):
    channels = page.rows(
        "channels",
        ready_im_channels(domain).order_by("name", "id").values("id", "name"),
    )
    accessible = _ready_channels(domain, user=user, ids=[row["id"] for row in channels])
    return {
        "groups": page.rows("groups", HandlerGroup.objects.filter(domain=domain).order_by("name", "id").values("id", "name")),
        "channels": [row for row in channels if row["id"] in accessible],
        "templates": page.rows(
            "templates",
            NotifyTemplate.objects.filter(domain=domain, channel_type__in=("site", "im"))
            .order_by("event", "channel_type", "id")
            .values("id", "event", "channel_type", "title_tpl"),
        ),
        "form_field_groups": _catalog_fields(schemas, person_form_fields),
    }
