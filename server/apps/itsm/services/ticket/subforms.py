"""子流程表单在父工单保存时生成子单，已关联子单不重复创建。"""

from hashlib import sha256

from django.db import transaction

from apps.itsm.models import Ticket, TicketRelation, WorkflowVersion


def materialize_subforms(service, ticket, schema, operator, *, initial=False):
    fields = list(schema.get("fields") or [])
    while fields:
        field = fields.pop()
        fields.extend(field.get("children") or [])
        if field.get("type") != "subProcessForm":
            continue
        rows = (ticket.form_data or {}).get(field["key"]) or []
        if len(rows) > 20:
            raise ValueError("每个子流程字段最多创建 20 个子单")
        if not rows:
            continue
        version = WorkflowVersion.objects.get(
            id=(field.get("props") or {}).get("workflow_version_id"), workflow__domain=ticket.domain, is_published=True
        )
        if version.workflow_id == ticket.workflow_id or ticket.related_from.filter(relation_type="child").exists():
            raise ValueError("子流程表单不允许递归创建子单")
        saved = []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError("子流程行必须是对象")
            if row.get("ticket_id"):
                relation = ticket.relations.select_related("related").filter(related_id=row["ticket_id"], relation_type="child").first()
                if relation is None:
                    raise ValueError("子单不属于当前工单")
                child = relation.related
            else:
                from apps.itsm.services.ticket.service import workflow_schema

                child_fields = workflow_schema(version).get("fields") or []
                if _contains_subform(child_fields):
                    raise ValueError("子流程表单不能嵌套创建子单")
                # 首次提单的子行属于同一份已持久化的输入，父单中断后复用同一个子单。
                key = sha256(f"{ticket.pk}:{field['key']}:{index}".encode()).hexdigest() if initial else None
                child = service.create(version, row.get("form_data") or {}, ticket.creator, is_test=ticket.is_test, creation_key=key)
                with transaction.atomic():
                    Ticket.objects.select_for_update().only("pk").get(pk=ticket.pk)
                    TicketRelation.objects.get_or_create(
                        ticket=ticket, related=child, relation_type="child",
                        defaults={"domain": ticket.domain, "created_by": operator, "updated_by": operator},
                    )
            saved.append({"ticket_id": child.id, "sn": child.sn, "form_data": child.form_data, "workflow_version_id": version.id})
        ticket.form_data[field["key"]] = saved


def _contains_subform(fields):
    return any(field.get("type") == "subProcessForm" or _contains_subform(field.get("children") or []) for field in fields or [])
