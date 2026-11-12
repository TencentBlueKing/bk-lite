from django.db import transaction
from django.utils import timezone

from apps.itsm.flowable.client import FlowableClient, FlowableError
from apps.itsm.models import StatusTransition, Ticket, TicketLog, TicketStatus, TicketTask, WorkflowVersion
from apps.itsm.services.form.validator import FormValidator
from apps.itsm.services.notify.service import dispatch_notification
from apps.itsm.services.sla import finish as finish_sla
from apps.itsm.services.sla import open_records, pause, resume
from apps.itsm.services.workflow.assignee import AssigneeBlocked, AssigneeResolver
from apps.itsm.signals import itsm_event


class TicketService:
    def __init__(self, client: FlowableClient | None = None):
        self.client = client

    @transaction.atomic
    def create(self, workflow_version: WorkflowVersion, form_data: dict, creator: str, is_test: bool = False) -> Ticket:
        schema = (
            workflow_version.workflow.form.current_version.schema
            if workflow_version.workflow.form_id and workflow_version.workflow.form.current_version_id
            else {"fields": []}
        )
        submit_node = _find_node(workflow_version.design, node_type="submit")
        if schema.get("fields"):
            form_data, errors = FormValidator(schema, _normalize_perm(submit_node.get("field_perm"))).apply(form_data)
            if errors:
                raise ValueError(errors)
        status = TicketStatus.objects.filter(key="new").first()
        ticket = Ticket.objects.create(
            sn=f"REQ{timezone.now().strftime('%Y%m%d%H%M%S%f')}",
            title=str(form_data.get("title") or workflow_version.workflow.name),
            workflow=workflow_version.workflow,
            workflow_version=workflow_version,
            status=status,
            creator=creator,
            form_data=form_data,
            is_test=is_test,
            created_by=creator,
            updated_by=creator,
        )
        open_records(ticket)
        TicketLog.objects.create(ticket=ticket, action="create", operator=creator, message="创建工单", created_by=creator, updated_by=creator)
        if self.client and workflow_version.process_definition_key:
            variables = {"initiator": creator, **self._assignee_variables(workflow_version, creator, form_data), **_form_variables(form_data)}
            started = self.client.start_process(workflow_version.process_definition_key, ticket.sn, variables)
            ticket.process_instance_id = str(started.get("id") or "")
            ticket.save(update_fields=["process_instance_id", "updated_at"])
            self.sync_ticket(ticket)
        return ticket

    def _assignee_variables(self, workflow_version: WorkflowVersion, creator: str, form_data: dict) -> dict:
        resolver = AssigneeResolver()
        context = {"initiator": creator, "form": form_data}
        variables = {}
        for node in (workflow_version.design or {}).get("nodes") or []:
            if node.get("type") not in {"approval", "handle", "manual", "subprocess_handle"}:
                continue
            try:
                people = resolver.resolve(node, context)
            except AssigneeBlocked as exc:
                raise ValueError(f"节点 {exc} 没有处理人") from exc
            if (node.get("multi") or {}).get("mode"):
                variables[f"itsm_assignees_{node['id']}"] = people
            elif people:
                variables[f"itsm_assignee_{node['id']}"] = people[0]
        if (workflow_version.design or {}).get("settings", {}).get("pre_approve"):
            variables["itsm_assignee_pre_approve"] = "admin"
        return variables

    def sync_ticket(self, ticket: Ticket) -> None:
        if not self.client or not ticket.process_instance_id:
            return
        try:
            items = self.client.list_tasks_including_children(ticket.process_instance_id)
        except FlowableError:
            return
        seen = set()
        for item in items:
            task_id = str(item.get("id") or "")
            seen.add(task_id)
            assignee = str(item.get("assignee") or "").strip('"')
            task, created = TicketTask.objects.get_or_create(
                ticket=ticket,
                flowable_task_id=task_id,
                defaults={
                    "node_id": item.get("taskDefinitionKey") or "",
                    "node_name": item.get("name") or "",
                    "assignee": assignee,
                    "created_by": "system",
                    "updated_by": "system",
                },
            )
            if created:
                entered = _find_node(ticket.workflow_version.design if ticket.workflow_version_id else {}, node_id=task.node_id)
                if entered.get("enter_status"):
                    self._set_status(ticket, entered["enter_status"])
            if created and entered.get("auto_return") and not getattr(ticket, "_auto_returning", False):
                rule = entered["auto_return"] if isinstance(entered.get("auto_return"), dict) else {}
                current = (ticket.form_data or {}).get(rule.get("field"))
                if rule.get("field") and str(current) == str(rule.get("value")):
                    ticket._auto_returning = True
                    self.operate(ticket, task, "return", {"return_mode": "submit", "opinion": "自动退回"}, "system")
            if created and task.assignee:
                itsm_event.send(
                    sender=ticket,
                    event="task.created",
                    receivers=[task.assignee],
                    variables={"title": ticket.title, "node": task.node_name, "url": f"/itsm/tickets/{ticket.id}"},
                    event_key=f"itsm-task-{task.flowable_task_id}",
                )
                from apps.itsm.services.todo_sync import push_todo

                push_todo(ticket, task)
        ticket.tasks.filter(status=TicketTask.TaskStatus.PENDING).exclude(flowable_task_id__in=seen).update(status=TicketTask.TaskStatus.DONE)

    @transaction.atomic
    def operate(self, ticket: Ticket, task: TicketTask, action: str, data: dict, operator: str) -> Ticket:
        if action not in {
            "submit",
            "approve",
            "reject",
            "claim",
            "suspend",
            "resume",
            "withdraw",
            "return",
            "transfer",
            "terminate",
            "close",
            "reopen",
            "urge",
            "save",
            "respond",
        }:
            raise ValueError("不支持的动作")
        if action in {"suspend", "resume", "withdraw", "return", "transfer", "terminate", "close", "reopen", "urge", "save", "respond"}:
            return self._side_action(ticket, task, action, data, operator)
        if task is None:
            raise ValueError("需要待办任务")
        task.status = TicketTask.TaskStatus.CLAIMED if action == "claim" else TicketTask.TaskStatus.DONE
        task.assignee = operator
        task.save(update_fields=["status", "assignee", "updated_at"])
        if action == "claim" and self.client and task.flowable_task_id:
            self.client.update_task_assignee(task.flowable_task_id, operator)
        node = _find_node(ticket.workflow_version.design if ticket.workflow_version_id else {}, node_id=task.node_id)
        incoming = data.get("form_data") if isinstance(data.get("form_data"), dict) else {}
        if incoming and _ticket_schema(ticket).get("fields"):
            schema = _ticket_schema(ticket)
            merged = dict(ticket.form_data or {})
            merged.update(incoming)
            cleaned, errors = FormValidator(schema, _normalize_perm(node.get("field_perm"))).apply(merged)
            if errors:
                raise ValueError(errors)
            merged.update(cleaned)
            ticket.form_data = merged
            ticket.save(update_fields=["form_data", "updated_at"])
        TicketLog.objects.create(
            ticket=ticket,
            task=task,
            action=action,
            operator=operator,
            detail=data,
            message=data.get("opinion") or action,
            created_by=operator,
            updated_by=operator,
        )
        from apps.itsm.services.triggers import fire_triggers

        fire_triggers(ticket, action, operator)
        if action in {"submit", "approve", "reject"}:
            finish_sla(ticket, "response")
        if action != "claim" and self.client and task.flowable_task_id:
            self.client.complete_task(
                task.flowable_task_id,
                {"result": action, f"out_{task.node_id}_result": action, **_form_variables(ticket.form_data)},
            )
            self.sync_ticket(ticket)
            if not self._process_active(ticket.process_instance_id):
                finished = TicketStatus.objects.filter(key="finished").first()
                if finished:
                    ticket.status = finished
                    ticket.save(update_fields=["status", "updated_at"])
                    finish_sla(ticket, "resolve")
                    from apps.itsm.models.extend import SurveyTemplate

                    if SurveyTemplate.objects.exists():
                        TicketLog.objects.create(
                            ticket=ticket,
                            action="survey_ready",
                            operator=operator,
                            message="请填写满意度",
                            created_by=operator,
                            updated_by=operator,
                        )
        return ticket

    def _side_action(self, ticket: Ticket, task: TicketTask | None, action: str, data: dict, operator: str) -> Ticket:
        if action == "suspend":
            self._set_status(ticket, "suspended")
            pause(ticket)
        elif action == "resume":
            resume(ticket)
            self._set_status(ticket, "processing")
        elif action == "withdraw":
            if self.client and ticket.process_instance_id:
                self.client.delete_process_instance(ticket.process_instance_id)
            ticket.tasks.filter(status=TicketTask.TaskStatus.PENDING).update(status=TicketTask.TaskStatus.DONE)
            self._set_status(ticket, "cancelled")
            finish_sla(ticket, "response")
            finish_sla(ticket, "resolve")
        elif action == "terminate":
            self._stop_process(ticket, "terminated")
        elif action == "close":
            self._stop_process(ticket, "finished")
        elif action == "reopen":
            self._set_status(ticket, "processing")
            version = ticket.workflow_version if ticket.workflow_version_id else None
            active = bool(self.client and ticket.process_instance_id and self._process_active(ticket.process_instance_id))
            open_status = [TicketTask.TaskStatus.PENDING, TicketTask.TaskStatus.CLAIMED]
            if self.client and version and version.process_definition_key and not active:
                variables = {
                    "initiator": ticket.creator,
                    **self._assignee_variables(version, ticket.creator, ticket.form_data or {}),
                    **_form_variables(ticket.form_data or {}),
                }
                started = self.client.start_process(version.process_definition_key, ticket.sn, variables)
                ticket.process_instance_id = str(started.get("id") or "")
                ticket.save(update_fields=["process_instance_id", "updated_at"])
                ticket.tasks.filter(status__in=open_status).update(status=TicketTask.TaskStatus.DONE)
                self.sync_ticket(ticket)
            elif not ticket.tasks.filter(status__in=open_status).exists():
                TicketTask.objects.create(
                    ticket=ticket,
                    node_id="reopen",
                    node_name="重新打开",
                    assignee=operator,
                    created_by=operator,
                    updated_by=operator,
                )
        elif action == "urge":
            receivers = [
                name
                for name in ticket.tasks.filter(status__in=[TicketTask.TaskStatus.PENDING, TicketTask.TaskStatus.CLAIMED]).values_list(
                    "assignee", flat=True
                )
                if name
            ]
            dispatch_notification(
                "ticket.urge",
                {"title": ticket.title, "url": f"/itsm/tickets/{ticket.id}", "content": data.get("opinion") or "请尽快处理"},
                receivers or [ticket.creator],
                event_key=f"itsm-urge-{ticket.id}-{int(timezone.now().timestamp())}",
            )
        elif action == "respond":
            self._set_status(ticket, "processing")
        elif action == "save":
            incoming = data.get("form_data") if isinstance(data.get("form_data"), dict) else {}
            if incoming:
                merged = dict(ticket.form_data or {})
                merged.update(incoming)
                ticket.form_data = merged
                ticket.save(update_fields=["form_data", "updated_at"])
        elif action == "transfer":
            if task is None:
                raise ValueError("需要待办任务")
            target = str(data.get("target") or "").strip()
            if not target:
                raise ValueError("需要转单目标")
            if self.client and task.flowable_task_id:
                self.client.update_task_assignee(task.flowable_task_id, target)
            task.assignee = target
            task.save(update_fields=["assignee", "updated_at"])
        elif action == "return":
            if task is None:
                raise ValueError("需要待办任务")
            mode = str(data.get("return_mode") or "submit")
            target_node = "submit"
            if mode == "previous":
                previous = ticket.tasks.filter(status=TicketTask.TaskStatus.DONE).exclude(node_id=task.node_id).order_by("-id").first()
                if previous is None:
                    raise ValueError("没有上一节点")
                target_node = previous.node_id
            elif mode != "submit":
                raise ValueError("退回模式只支持 submit 或 previous")
            if self.client and ticket.process_instance_id and task.node_id:
                self.client.change_state(ticket.process_instance_id, [task.node_id], [target_node])
            task.status = TicketTask.TaskStatus.DONE
            task.save(update_fields=["status", "updated_at"])
            self._set_status(ticket, "new" if target_node == "submit" else "processing")
            if self.client:
                self.sync_ticket(ticket)
        self._log(ticket, task, action, data, operator)
        return ticket

    def _stop_process(self, ticket: Ticket, status_key: str) -> None:
        if self.client and ticket.process_instance_id:
            try:
                self.client.delete_process_instance(ticket.process_instance_id)
            except FlowableError:
                pass
        ticket.tasks.filter(status=TicketTask.TaskStatus.PENDING).update(status=TicketTask.TaskStatus.DONE)
        self._set_status(ticket, status_key)
        finish_sla(ticket, "response")
        finish_sla(ticket, "resolve")
        if status_key == "finished":
            from apps.itsm.models.extend import SurveyTemplate

            if SurveyTemplate.objects.exists():
                TicketLog.objects.create(
                    ticket=ticket,
                    action="survey_ready",
                    operator=ticket.updated_by or ticket.creator,
                    message="请填写满意度",
                    created_by=ticket.creator,
                    updated_by=ticket.creator,
                )

    def _set_status(self, ticket: Ticket, key: str) -> None:
        if ticket.status_id and ticket.status.key == key:
            return
        status = TicketStatus.objects.filter(key=key).first()
        if status is None:
            raise ValueError(f"缺少状态 {key}")
        current_key = ticket.status.key if ticket.status_id else ""
        allowed = set(StatusTransition.objects.filter(from_status__key=current_key).values_list("to_status__key", flat=True))
        if allowed and key not in allowed:
            raise ValueError(f"不允许从 {current_key} 转到 {key}")
        ticket.status = status
        ticket.save(update_fields=["status", "updated_at"])

    def _log(self, ticket: Ticket, task: TicketTask | None, action: str, data: dict, operator: str) -> None:
        TicketLog.objects.create(
            ticket=ticket,
            task=task,
            action=action,
            operator=operator,
            detail=data,
            message=data.get("opinion") or data.get("target") or action,
            created_by=operator,
            updated_by=operator,
        )
        from apps.itsm.services.triggers import fire_triggers

        fire_triggers(ticket, action, operator)

    def _process_active(self, process_instance_id: str) -> bool:
        if not self.client or not process_instance_id:
            return False
        try:
            payload = self.client.get_process_instance(process_instance_id)
        except FlowableError as exc:
            return exc.status != 404
        if payload.get("ended"):
            return False
        try:
            historic = self.client._request("GET", f"/flowable-rest/service/history/historic-process-instances/{process_instance_id}")
        except FlowableError:
            return True
        return not historic.get("endTime")

    def finish_if_ended(self, ticket: Ticket) -> None:
        if ticket.status_id and ticket.status.key in {"finished", "terminated", "cancelled"}:
            return
        if self._process_active(ticket.process_instance_id):
            return
        finished = TicketStatus.objects.filter(key="finished").first()
        if finished is None:
            return
        self._set_status(ticket, "finished")
        finish_sla(ticket, "resolve")


_PERM_ALIAS = {"edit": "editable", "read": "readonly"}


def _form_variables(form_data: dict) -> dict:
    variables = {}
    for key, value in (form_data or {}).items():
        if isinstance(value, (str, int, float, bool)):
            variables[f"form_{key}"] = value
    return variables


def _normalize_perm(perm) -> dict:
    return {key: _PERM_ALIAS.get(value, value) for key, value in (perm or {}).items()}


def _find_node(design, node_id=None, node_type=None) -> dict:
    for node in (design or {}).get("nodes") or []:
        if node_id and node.get("id") == node_id:
            return node
        if node_type and node.get("type") == node_type:
            return node
    return {}


def _ticket_schema(ticket) -> dict:
    workflow = ticket.workflow
    if workflow.form_id and workflow.form.current_version_id:
        return workflow.form.current_version.schema or {"fields": []}
    return {"fields": []}
