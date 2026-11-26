"""子流程表单在父工单保存时生成子单，已关联子单不重复创建。"""

from hashlib import sha256

from django.db import transaction

from apps.itsm.models import Ticket, TicketRelation, WorkflowVersion
from apps.itsm.services.form.fetch import walk


def has_subform_rows(schema, values, *, only_unprepared=False):
    for field in walk(schema.get("fields") or []):
        if field.get("type") != "subProcessForm":
            continue
        rows = values.get(field["key"]) or []
        if rows and (not only_unprepared or not isinstance(rows, list) or any(not isinstance(row, dict) or not row.get("ticket_id") for row in rows)):
            return True
    return False


def prepare_initial_subforms(service, ticket, schema):
    # 调用方持有父单事务。全部子行通过校验后才允许 on_commit 启动子流程。
    materialize_subforms(service, ticket, schema, ticket.creator, initial=True, defer_children=True)
    ticket.save(update_fields=["form_data", "updated_at"])


def materialize_subforms(service, ticket, schema, operator, *, initial=False, operation_key=None, defer_children=False):
    fields = list(schema.get("fields") or [])
    while fields:
        field = fields.pop()
        fields.extend(field.get("children") or [])
        if field.get("type") != "subProcessForm":
            continue
        rows = (ticket.form_data or {}).get(field["key"]) or []
        if not isinstance(rows, list):
            raise ValueError("子流程字段必须为列表")
        if len(rows) > 20:
            raise ValueError("每个子流程字段最多创建 20 个子单")
        if not rows:
            continue
        version = WorkflowVersion.objects.filter(
            id=(field.get("props") or {}).get("workflow_version_id"), workflow__domain=ticket.domain, is_published=True
        ).first()
        if version is None:
            raise ValueError("子流程表单使用的已发布版本不存在")
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
                if (initial or operation_key) and not defer_children and child.creation_state != "complete":
                    if not child.creation_key:
                        raise ValueError("关联子单缺少创建记录，请先核对子单")
                    child = service.create(
                        child.workflow_version,
                        child.form_data,
                        child.creator,
                        is_test=child.is_test,
                        creation_key=child.creation_key,
                        service=child.service,
                    )
            else:
                from apps.itsm.services.ticket.service import workflow_schema

                child_fields = workflow_schema(version).get("fields") or []
                if _contains_subform(child_fields):
                    raise ValueError("子流程表单不能嵌套创建子单")
                # 首次提单的子行属于同一份已持久化的输入，父单中断后复用同一个子单。
                key = None
                if initial or operation_key:
                    namespace = str(ticket.pk) if initial else f"{ticket.pk}:{operation_key}"
                    key = sha256(f"{namespace}:{field['key']}:{index}".encode()).hexdigest()
                child = service.create(
                    version,
                    row.get("form_data") or {},
                    ticket.creator,
                    is_test=ticket.is_test,
                    creation_key=key,
                    defer_start=defer_children or (not initial and not operation_key),
                )
                with transaction.atomic():
                    Ticket.objects.select_for_update().only("pk").get(pk=ticket.pk)
                    TicketRelation.objects.get_or_create(
                        ticket=ticket,
                        related=child,
                        relation_type="child",
                        defaults={"domain": ticket.domain, "created_by": operator, "updated_by": operator},
                    )
            saved.append({"ticket_id": child.id, "sn": child.sn, "form_data": child.form_data, "workflow_version_id": version.id})
        ticket.form_data[field["key"]] = saved


def _contains_subform(fields):
    return any(field.get("type") == "subProcessForm" or _contains_subform(field.get("children") or []) for field in fields or [])
