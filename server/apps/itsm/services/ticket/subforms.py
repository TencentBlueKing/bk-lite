"""子流程表单在父工单保存时生成子单，已关联子单不重复创建。"""

from apps.itsm.models import TicketRelation, WorkflowVersion


def materialize_subforms(service, ticket, schema, operator):
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
        for row in rows:
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
                child = service.create(version, row.get("form_data") or {}, ticket.creator, is_test=ticket.is_test)
                TicketRelation.objects.create(
                    ticket=ticket, related=child, relation_type="child", domain=ticket.domain, created_by=operator, updated_by=operator
                )
            saved.append({"ticket_id": child.id, "sn": child.sn, "form_data": child.form_data, "workflow_version_id": version.id})
        ticket.form_data[field["key"]] = saved
    ticket.save(update_fields=["form_data", "updated_at"])


def _contains_subform(fields):
    return any(field.get("type") == "subProcessForm" or _contains_subform(field.get("children") or []) for field in fields or [])
