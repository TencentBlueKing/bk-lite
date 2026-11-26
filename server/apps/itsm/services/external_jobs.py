"""外部作业执行与 ACK 分离；失败不推进，重复领取不重复业务动作。"""

from datetime import timedelta
from uuid import uuid4

from django.db import connection, transaction
from django.utils import timezone

from apps.itsm.flowable.client import FlowableError
from apps.itsm.models import AutoExecution, DecisionTable, KnowledgeArticle, Ticket, TicketLog
from apps.itsm.services.auto_runner import run_auto_action
from apps.itsm.services.form.rules import match_when
from apps.itsm.services.ticket.actions import validated_opinion
from apps.itsm.services.ticket.service import TicketService, _find_node, _form_variables

TERMINAL = {"finished", "terminated", "cancelled", "suspended"}
LOCAL_ACTIONS = {"table", "cmdb"}
LOCAL_NODES = {"decision", "knowledge", "auto_dispatch"}


class ActionFailure(Exception):
    def __init__(self, reason, *, retryable=False):
        super().__init__(reason)
        self.retryable = retryable


def retry_available(ticket, execution):
    detail = execution.detail
    return bool(
        execution.kind == "external"
        and detail.get("process_id") == ticket.process_instance_id
        and ticket.process_instance_id
        and (not ticket.status_id or ticket.status.key not in TERMINAL)
        and (
            execution.status == "failed"
            and detail.get("retryable")
            or execution.status == "executed"
            and detail.get("reason")
            and not detail.get("retry_requested")
        )
    )


@transaction.atomic
def request_retry(ticket, execution_id, operator):
    ticket = Ticket.objects.select_for_update().get(pk=ticket.pk)
    execution = ticket.auto_executions.select_for_update().get(pk=execution_id)
    if execution.detail.get("process_id") != ticket.process_instance_id or (ticket.status_id and ticket.status.key in TERMINAL):
        return False
    if execution.status == "queued" or (execution.status == "executed" and execution.detail.get("retry_requested")):
        return True
    if not retry_available(ticket, execution):
        return False
    if execution.status == "failed":
        execution.status = "queued"
    execution.detail = {**execution.detail, "retry_requested": True}
    execution.save(update_fields=["status", "detail", "updated_at"])
    TicketLog.objects.create(
        ticket=ticket,
        domain=ticket.domain,
        action="auto_retry",
        operator=operator,
        message="请求重试自动节点",
        detail={"node_id": execution.detail["node_id"], "execution_id": execution.id},
        created_by=operator,
        updated_by=operator,
    )
    return True


def _local_action(node):
    return node.get("type") in LOCAL_NODES or (node.get("auto") or {}).get("kind") in LOCAL_ACTIONS


def _external_effect(node):
    return node.get("type") in {"cc", "notice"} or (node.get("auto") or {}).get("kind") in {"integration", "http", "job", "workflow"}


def review_available(ticket, execution):
    if (
        execution.kind != "external"
        or not ticket.process_instance_id
        or execution.detail.get("process_id") != ticket.process_instance_id
        or (ticket.status_id and ticket.status.key in TERMINAL)
    ):
        return False
    if execution.status == "unknown":
        return True
    return (
        execution.status == "failed"
        and not execution.detail.get("retryable")
        and _external_effect(_job_node(ticket, execution.detail.get("node_id", "")))
    )


def result_field(ticket, execution):
    config = _job_node(ticket, execution.detail.get("node_id", "")).get("auto") or {}
    return config.get("result_field") if config.get("kind") == "integration" else None


@transaction.atomic
def reconcile_execution(ticket, execution_id, operator, payload):
    ticket = Ticket.objects.select_for_update().get(pk=ticket.pk)
    execution = ticket.auto_executions.select_for_update().get(pk=execution_id)
    if not review_available(ticket, execution) or payload.get("review_token") != execution.updated_at.isoformat():
        return False
    opinion = validated_opinion(payload.get("note"), required=True)
    outcome = payload.get("outcome")
    if outcome not in ("executed", "not_executed"):
        raise ValueError("请指定核对结果")
    if outcome == "executed":
        field = result_field(ticket, execution)
        if field:
            if "result_value" not in payload:
                raise ValueError("请提供已核实的外部返回值")
            ticket.form_data = {**ticket.form_data, field: payload["result_value"]}
            ticket.save(update_fields=["form_data", "updated_at"])
        execution.status = "executed"
    else:
        execution.status = "queued"
    execution.detail = {key: value for key, value in execution.detail.items() if key not in {"reason", "retryable"}}
    execution.detail["retry_requested"] = True
    execution.save(update_fields=["status", "detail", "updated_at"])
    TicketLog.objects.create(
        ticket=ticket,
        domain=ticket.domain,
        operator=operator,
        action="auto_reconcile",
        message="已核实外部动作成功，等待推进流程" if outcome == "executed" else "已核实外部动作未执行，等待重新执行",
        detail={
            "node_id": execution.detail["node_id"],
            "execution_id": execution.pk,
            "job_id": execution.detail["job_id"],
            "outcome": outcome,
            "opinion": opinion,
        },
        created_by=operator,
        updated_by=operator,
    )
    return True


def reconcile_stale_executions(client, limit=100):
    recovered = _recover_interrupted_actions(limit)
    return recovered + _recover_acknowledgements(client, limit)


@transaction.atomic
def _recover_interrupted_actions(limit):
    stale = AutoExecution.objects.filter(kind="external", status="running", updated_at__lte=timezone.now() - timedelta(minutes=5))
    # 慢调用持有工单锁直到业务结果落库。跳过在执行的工单，并在锁内重查状态。
    tickets = (
        Ticket.objects.filter(pk__in=stale.values("ticket_id"))
        .order_by("pk")
        .select_for_update(skip_locked=connection.features.has_select_for_update_skip_locked)
    )
    recovered = 0
    for ticket in tickets[:limit]:
        for execution in stale.filter(ticket_id=ticket.pk):
            node = _job_node(ticket, execution.detail.get("node_id", ""))
            if execution.detail.get("process_id") != ticket.process_instance_id or (
                ticket.status_id and ticket.status.key in TERMINAL - {"suspended"}
            ):
                execution.status = "failed"
                reason = "原流程已结束或切换，请核对历史执行记录"
            elif _local_action(node):
                execution.status = "queued"
                reason = "本地事务已回滚，等待重新执行"
            else:
                execution.status = "unknown"
                reason = "执行中断，请核实下游动作的实际结果"
            execution.detail = {**execution.detail, "reason": reason, "retryable": False}
            execution.save(update_fields=["status", "detail", "updated_at"])
            recovered += 1
    return recovered


def execute_node(ticket, node, *, job_id=None):
    kind = node.get("type")
    config = node.get("auto") or {}
    if kind in {"cc", "notice"}:
        from apps.itsm.services.notify.service import dispatch_notification, ticket_notice_variables

        receivers = config.get("receivers") or (node.get("assignee") or {}).get("value") or []
        if not receivers:
            raise ActionFailure("通知节点缺少接收人", retryable=True)
        if not job_id:
            raise ActionFailure("通知作业缺少标识")
        result = dispatch_notification(
            "node.notice",
            {
                **ticket_notice_variables(ticket),
                "title": ticket.title,
                "content": config.get("content") or ticket.title,
                "node": node.get("name") or node["id"],
            },
            receivers,
            event_key=f"itsm-notice-{ticket.id}-{job_id}",
            site_only=ticket.is_test,
            domain=ticket.domain,
        )
        if not (result.get("site") or {}).get("result"):
            raise ActionFailure("通知投递结果待核对")
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
        content = str(ticket.form_data.get(config.get("content_field") or "content") or config.get("content") or "")
        if not KnowledgeArticle.has_publishable_content(content, KnowledgeArticle.ContentFormat.TEXT):
            raise ActionFailure("发布前请填写正文", retryable=True)
        article = KnowledgeArticle.objects.create(
            domain=ticket.domain,
            title=ticket.title,
            content=content,
            status="published",
            created_by=ticket.creator,
            updated_by=ticket.creator,
        )
        article.tickets.add(ticket)
        return {"article_id": article.id}
    if kind == "auto_dispatch":
        variables = TicketService()._assignee_variables(ticket.workflow_version, ticket.creator, ticket.form_data, service_id=ticket.service_id)
        return {"variables": variables}
    if kind == "rule_trigger" and not match_when(config.get("when"), ticket.form_data):
        return {"skipped": True, "reason": "未满足触发条件"}
    if kind not in {"auto", "manual_trigger", "rule_trigger"}:
        raise ActionFailure("找不到已发布的自动节点配置", retryable=True)
    status, detail = run_auto_action(ticket, str(config.get("kind") or ""), config, "system")
    if status != "done":
        if status == "skipped":
            raise ActionFailure(detail.get("reason") or "自动动作尚未配置", retryable=True)
        if config.get("kind") == "http" and isinstance(detail.get("status_code"), int):
            raise ActionFailure(f"外部接口返回 HTTP {detail['status_code']}，请核对处理结果")
        raise ActionFailure("自动动作未确认成功，请核对外部处理结果", retryable=config.get("kind") in LOCAL_ACTIONS)
    return detail


def _job_node(ticket, element_id):
    design = ticket.workflow_version.design if ticket.workflow_version_id else {}
    node = _find_node(design, node_id=element_id)
    if not node and element_id.endswith("__action"):
        original = _find_node(design, node_id=element_id[:-8])
        if original.get("type") == "manual_trigger":
            return original
    return node


def _execute(ticket, execution, node, detail):
    try:
        with transaction.atomic():
            ticket = Ticket.objects.select_for_update().get(pk=ticket.pk)
            if not AutoExecution.objects.filter(pk=execution.pk, status="running", detail__attempt=detail["attempt"]).exists():
                return
            if ticket.process_instance_id != detail["process_id"] or (
                ticket.status_id and ticket.status.key in {"finished", "terminated", "cancelled"}
            ):
                raise ActionFailure("流程已结束或切换，本次动作未执行")
            if ticket.status_id and ticket.status.key == "suspended":
                execution.status = "queued"
                execution.save(update_fields=["status", "updated_at"])
                return
            result = execute_node(ticket, node, job_id=detail["job_id"])
            execution.status = "executed"
            execution.detail = {**detail, "result": result}
            execution.save(update_fields=["status", "detail", "updated_at"])
    except Exception as exc:
        is_local = _local_action(node)
        retryable = exc.retryable if isinstance(exc, ActionFailure) else is_local
        execution.status = "unknown" if _external_effect(node) and not retryable else "failed"
        execution.detail = {
            **detail,
            "reason": str(exc) if isinstance(exc, ActionFailure) else f"自动动作执行失败（{type(exc).__name__}）",
            "retryable": retryable,
        }
        AutoExecution.objects.filter(pk=execution.pk, status="running", detail__attempt=detail["attempt"]).update(
            status=execution.status, detail=execution.detail, updated_at=timezone.now()
        )


def _ack_marker(execution):
    # 工单表单变量使用 form_ 前缀。每份收据独立命名，循环经过同一节点也能区分。
    return f"__bk_itsm_ack_{execution.pk}", f"{execution.detail['job_id']}:{execution.detail.get('attempt', '')}"


def _completed_detail(detail):
    return {key: value for key, value in detail.items() if key not in {"reason", "retry_requested"}}


def _recover_acknowledgements(client, limit):
    # 每页轮换；引擎只读核对在数据库事务之外。较早且尚无回执的记录不会阻塞后续工单。
    stale = AutoExecution.objects.filter(kind="external", status="executed", updated_at__lte=timezone.now() - timedelta(minutes=5))
    recovered = 0
    for execution in stale.order_by("updated_at", "pk")[:limit]:
        detail = execution.detail
        confirmed = False
        if detail.get("job_id") and detail.get("process_id"):
            try:
                confirmed = client.confirmed_external_job(detail["process_id"], *_ack_marker(execution))
            except FlowableError:
                pass
        changes = {"updated_at": timezone.now()}
        if confirmed:
            changes.update(status="done", detail=_completed_detail(detail))
        updated = AutoExecution.objects.filter(pk=execution.pk, status="executed", updated_at=execution.updated_at).update(**changes)
        if confirmed:
            recovered += updated
    return recovered


@transaction.atomic
def _ack(client, ticket, execution_id):
    ticket = Ticket.objects.select_for_update().get(pk=ticket.pk)
    execution = ticket.auto_executions.select_for_update().get(pk=execution_id)
    if execution.status == "done":
        return True
    detail = execution.detail
    if detail.get("process_id") != ticket.process_instance_id or (ticket.status_id and ticket.status.key in TERMINAL):
        return False
    variables = {**_form_variables(ticket.form_data, ticket.workflow_version), **(detail.get("result", {}).get("variables") or {})}
    marker, value = _ack_marker(execution)
    variables[marker] = value
    try:
        client.complete_external_job(detail["job_id"], variables=variables)
    except FlowableError:
        execution.detail = {**detail, "reason": "动作已完成，流程推进结果待核对", "retry_requested": False}
        execution.save(update_fields=["detail", "updated_at"])
        return False
    execution.status = "done"
    execution.detail = _completed_detail(detail)
    execution.save(update_fields=["status", "detail", "updated_at"])
    return True


def process_job(client, job):
    job_id = str(job.get("id") or "")
    process_id = str(job.get("processInstanceId") or "")
    if not job_id or not process_id:
        return False
    with transaction.atomic():
        ticket = Ticket.objects.select_for_update().filter(process_instance_id=process_id).first()
        if ticket is None or (ticket.status_id and ticket.status.key in TERMINAL):
            return False
        element_id = str(job.get("elementId") or "")
        node = _job_node(ticket, element_id)
        detail = {"job_id": job_id, "process_id": process_id, "node_id": node.get("id") or element_id, "attempt": uuid4().hex}
        execution = ticket.auto_executions.filter(detail__job_id=job_id).first()
        if execution is None:
            execution = AutoExecution.objects.create(
                ticket=ticket,
                domain=ticket.domain,
                kind="external",
                status="running",
                detail=detail,
            )
        elif execution.status == "queued":
            execution.status = "running"
            execution.detail = detail
            execution.save(update_fields=["status", "detail", "updated_at"])
        elif execution.status not in {"executed", "done"}:
            return False
        elif not execution.detail.get("process_id"):
            execution.detail = {**detail, **execution.detail}
            execution.save(update_fields=["detail", "updated_at"])
    if execution.status == "running":
        _execute(ticket, execution, node, detail)
        if execution.status != "executed":
            return False
    if not _ack(client, ticket, execution.id):
        return False
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
