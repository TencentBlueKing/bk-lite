from django.db import transaction
from django.utils import timezone

from apps.itsm.flowable.client import FlowableClient, FlowableError
from apps.itsm.models import Ticket, TicketLog, TicketStatus, TicketTask, WorkflowVersion
from apps.itsm.services.form.validator import FormValidator
from apps.itsm.services.notify.service import dispatch_notification
from apps.itsm.services.workflow.assignee import AssigneeResolver


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
        errors = FormValidator(schema).validate(form_data)
        if errors:
            raise ValueError(errors)
        status = TicketStatus.objects.filter(key="new").first()
        ticket = Ticket.objects.create(
            sn=f"REQ{timezone.now().strftime('%Y%m%d%H%M%S')}",
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
        TicketLog.objects.create(ticket=ticket, action="create", operator=creator, message="创建工单", created_by=creator, updated_by=creator)
        if self.client and workflow_version.process_definition_key:
            variables = {"initiator": creator, **self._assignee_variables(workflow_version, creator, form_data)}
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
            if node.get("type") not in {"approval", "handle"}:
                continue
            people = resolver.resolve(node, context)
            if (node.get("multi") or {}).get("mode"):
                variables[f"itsm_assignees_{node['id']}"] = people
            elif people:
                variables[f"itsm_assignee_{node['id']}"] = people[0]
        return variables

    def sync_ticket(self, ticket: Ticket) -> None:
        if not self.client or not ticket.process_instance_id:
            return
        try:
            payload = self.client.list_tasks(ticket.process_instance_id)
        except FlowableError:
            return
        seen = set()
        for item in payload.get("data") or []:
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
            if created and task.assignee:
                dispatch_notification("task.created", {"title": ticket.title, "node": task.node_name}, [task.assignee])
        ticket.tasks.filter(status=TicketTask.TaskStatus.PENDING).exclude(flowable_task_id__in=seen).update(status=TicketTask.TaskStatus.DONE)

    @transaction.atomic
    def operate(self, ticket: Ticket, task: TicketTask, action: str, data: dict, operator: str) -> Ticket:
        if action not in {"submit", "approve", "reject", "claim"}:
            raise ValueError("不支持的动作")
        task.status = TicketTask.TaskStatus.CLAIMED if action == "claim" else TicketTask.TaskStatus.DONE
        task.assignee = operator
        task.save(update_fields=["status", "assignee", "updated_at"])
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
        if action != "claim" and self.client and task.flowable_task_id:
            self.client.complete_task(task.flowable_task_id, {"result": action})
            self.sync_ticket(ticket)
            if not self._process_active(ticket.process_instance_id):
                finished = TicketStatus.objects.filter(key="finished").first()
                if finished:
                    ticket.status = finished
                    ticket.save(update_fields=["status", "updated_at"])
        return ticket

    def _process_active(self, process_instance_id: str) -> bool:
        if not self.client or not process_instance_id:
            return False
        try:
            self.client.get_process_instance(process_instance_id)
        except FlowableError as exc:
            return exc.status != 404
        return True
