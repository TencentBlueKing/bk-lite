"""外部作业执行与 ACK 分离；失败不推进，重复领取不重复业务动作。"""

from django.db import transaction

from apps.itsm.flowable.client import FlowableError
from apps.itsm.models import AutoExecution, DecisionTable, KnowledgeArticle, Ticket
from apps.itsm.services.auto_runner import run_auto_action
from apps.itsm.services.form.rules import match_when
from apps.itsm.services.ticket.service import TicketService, _find_node, _form_variables


def execute_node(ticket, node):
    kind = node.get("type")
    config = node.get("auto") or {}
    if kind in {"cc", "notice"}:
        from apps.itsm.services.notify.service import dispatch_notification

        receivers = config.get("receivers") or (node.get("assignee") or {}).get("value") or []
        if not receivers:
            raise ValueError("通知节点缺少接收人")
        result = dispatch_notification(
            "node.notice",
            {"title": ticket.title, "content": config.get("content") or ticket.title},
            receivers,
            event_key=f'itsm-notice-{ticket.id}-{node["id"]}-{ticket.process_instance_id}',
            site_only=ticket.is_test,
        )
        if not (result.get("site") or {}).get("result"):
            raise ValueError("站内通知未投递成功")
        return {"notified": True}
    if kind == "decision":
        table = DecisionTable.objects.get(id=config.get("decision_id"), domain=ticket.domain)
        rules = table.rules or []
        if isinstance(rules, dict):
            rows = rules.get("rows") or []
            rules = [
                {
                    "when": {
                        "logic": "and",
                        "items": [
                            dict(value, field=key) if isinstance(value, dict) else {"field": key, "op": "=", "value": value}
                            for key, value in (row.get("conditions") or {}).items()
                        ],
                    },
                    "then": row.get("results") or {},
                }
                for row in rows
            ]
        matched = next((rule.get("then") or {} for rule in rules if match_when(rule.get("when"), ticket.form_data)), {})
        ticket.form_data = {**ticket.form_data, **matched}
        ticket.save(update_fields=["form_data", "updated_at"])
        return {"matched_keys": list(matched)}
    if kind == "knowledge":
        article = KnowledgeArticle.objects.create(
            domain=ticket.domain,
            title=ticket.title,
            content=str(ticket.form_data.get(config.get("content_field") or "content") or config.get("content") or ""),
            status="published",
            created_by=ticket.creator,
            updated_by=ticket.creator,
        )
        return {"article_id": article.id}
    if kind == "auto_dispatch":
        variables = TicketService()._assignee_variables(ticket.workflow_version, ticket.creator, ticket.form_data)
        return {"variables": variables}
    if kind == "rule_trigger" and not match_when(config.get("when"), ticket.form_data):
        return {"skipped": True, "reason": "未满足触发条件"}
    if kind not in {"auto", "manual_trigger", "rule_trigger"}:
        raise ValueError("未知自动节点")
    status, detail = run_auto_action(ticket, str(config.get("kind") or ""), config, "system")
    if status != "done":
        raise ValueError("自动动作未完成")
    return detail


def process_job(client, job):
    job_id = str(job.get("id") or "")
    if not job_id:
        return False
    with transaction.atomic():
        ticket = Ticket.objects.select_for_update().filter(process_instance_id=str(job.get("processInstanceId") or "")).first()
        if ticket is None:
            return False
        execution = ticket.auto_executions.filter(detail__job_id=job_id).first()
        if execution is None:
            execution = AutoExecution.objects.create(
                ticket=ticket, domain=ticket.domain, kind="external", status="running", detail={"job_id": job_id}
            )
        elif execution.status in {"running", "failed"}:
            # 结果不确定时保留人工恢复入口，不能盲目重放远端动作。
            return False
    if execution.status == "running":
        try:
            with transaction.atomic():
                node = _find_node(ticket.workflow_version.design, node_id=job.get("elementId"))
                if not node and str(job.get("elementId") or "").endswith("__action"):
                    original = _find_node(ticket.workflow_version.design, node_id=job["elementId"][:-8])
                    if original.get("type") == "manual_trigger":
                        node = original
                result = execute_node(ticket, node)
                execution.status = "executed"
                execution.detail = {"job_id": job_id, "node_id": node.get("id"), "result": result}
                execution.save(update_fields=["status", "detail", "updated_at"])
        except Exception as exc:
            execution.status = "failed"
            execution.detail = {"job_id": job_id, "error_type": type(exc).__name__}
            execution.save(update_fields=["status", "detail", "updated_at"])
            return False
    if execution.status != "done":
        variables = {**_form_variables(ticket.form_data), **(execution.detail.get("result", {}).get("variables") or {})}
        try:
            client.complete_external_job(job_id, variables=variables)
        except FlowableError as exc:
            if exc.status != 404:
                return False
        execution.status = "done"
        execution.save(update_fields=["status", "updated_at"])
    service = TicketService(client)
    service.sync_ticket(ticket)
    service.finish_if_ended(ticket)
    return True


def reconcile_tickets(client, limit=100):
    """Flowable ACK 后可异步生成任务；有界轮询补齐后续任务与终态。"""
    from django.core.cache import cache

    key = "itsm:engine-reconcile-cursor"
    cursor = int(cache.get(key) or 0)
    queryset = Ticket.objects.exclude(process_instance_id="").exclude(status__key__in=["finished", "terminated", "cancelled"])
    ids = list(queryset.filter(id__gt=cursor).order_by("id").values_list("id", flat=True)[:limit])
    if not ids:
        ids = list(queryset.order_by("id").values_list("id", flat=True)[:limit])
    service = TicketService(client)
    for ticket in Ticket.objects.filter(id__in=ids):
        try:
            service.sync_ticket(ticket)
            service.finish_if_ended(ticket)
        except FlowableError:
            continue
    cache.set(key, max(ids) if ids else 0, timeout=600)
    return len(ids)
