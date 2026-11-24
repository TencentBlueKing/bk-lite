from uuid import uuid4

from django.db import transaction
from django.utils import timezone

from apps.itsm.flowable.client import FlowableClient, FlowableError
from apps.itsm.models import Service, StatusTransition, Ticket, TicketLog, TicketStatus, TicketTask, WorkflowVersion
from apps.itsm.services.form.fetch import task_fetch_context, validate_submission
from apps.itsm.services.notify.service import dispatch_notification, ticket_notice_variables
from apps.itsm.services.sla import finish as finish_sla
from apps.itsm.services.sla import open_records, pause, resume
from apps.itsm.services.ticket.actions import (
    TASK_ACTIONS,
    NodeActionValidationError,
    node_actions,
    node_required_opinions,
    side_action_enabled,
    side_required_opinions,
    validated_opinion,
)
from apps.itsm.services.ticket.returns import resolve_return_target
from apps.itsm.services.ticket.survey import record_survey_invitation
from apps.itsm.services.ticket.transfer import require_transfer_target, transfer_users
from apps.itsm.services.todo_sync import schedule_sync
from apps.itsm.services.workflow.assignee import AssigneeBlocked, AssigneeResolver
from apps.itsm.signals import itsm_event


class TaskAssigneeChanged(ValueError):
    pass


class TransferRejected(ValueError):
    pass


class TicketService:
    def __init__(self, client: FlowableClient | None = None, identity=None):
        self.client = client
        self.identity = identity

    def create(
        self,
        workflow_version: WorkflowVersion,
        form_data: dict,
        creator: str,
        is_test: bool = False,
        *,
        service: Service | None = None,
        creation_key: str | None = None,
        defer_start: bool = False,
    ) -> Ticket:
        from apps.itsm.services.ticket.subforms import has_subform_rows, prepare_initial_subforms

        if creation_key is not None and (not isinstance(creation_key, str) or not creation_key.strip() or len(creation_key) > 128):
            raise ValueError("申请标识无效")
        key = {"domain": workflow_version.domain, "creator": creator, "creation_key": creation_key or uuid4().hex}
        ticket = Ticket.objects.filter(**key).first()
        schema = workflow_schema(workflow_version)
        if ticket is None:
            submit_node = _find_node(workflow_version.design, node_type="submit")
            if schema.get("fields"):
                form_data = validate_submission(
                    schema,
                    form_data,
                    self.identity,
                    f"version:{workflow_version.id}",
                    field_perm=_normalize_perm(submit_node.get("field_perm")),
                )
            with transaction.atomic():
                ticket, created = Ticket.objects.get_or_create(
                    **key,
                    defaults={
                        "sn": f"REQ{timezone.now().strftime('%Y%m%d%H%M%S%f')}",
                        "title": str(form_data.get("title") or workflow_version.workflow.name),
                        "workflow": workflow_version.workflow,
                        "workflow_version": workflow_version,
                        "service": service,
                        "status": TicketStatus.objects.filter(key="new").first(),
                        "form_data": form_data,
                        "is_test": is_test or bool((workflow_version.design or {}).get("settings", {}).get("is_test")),
                        "created_by": creator,
                        "updated_by": creator,
                        "creation_state": "prepared",
                    },
                )
                if created:
                    if has_subform_rows(schema, ticket.form_data):
                        prepare_initial_subforms(self, ticket, schema)
                    open_records(ticket)
                    TicketLog.objects.create(
                        ticket=ticket, domain=ticket.domain, action="create", operator=creator, message="创建工单", created_by=creator, updated_by=creator
                    )
        if ticket.workflow_version_id != workflow_version.pk or ticket.service_id != (service.pk if service else None):
            raise ValueError("申请标识已用于其他服务或版本")
        if ticket.creation_state == "complete":
            return ticket
        if defer_start and (
            workflow_version.process_definition_key or workflow_version.process_definition_id or workflow_version.flowable_deployment_id
        ):
            transaction.on_commit(lambda: self._resume_creation(Ticket.objects.get(pk=ticket.pk)), robust=True)
            return ticket
        return self._resume_creation(ticket)

    def _resume_creation(self, ticket):
        from apps.itsm.services.ticket.start_recovery import initial_start
        from apps.itsm.services.ticket.subforms import has_subform_rows, materialize_subforms, prepare_initial_subforms

        if ticket.creation_state == "complete":
            return ticket
        workflow_version = ticket.workflow_version
        schema = workflow_schema(workflow_version)
        if has_subform_rows(schema, ticket.form_data, only_unprepared=True):
            # 旧版本留下的草稿可能只有原始子行。恢复时先补齐同一套校验和预建。
            with transaction.atomic():
                ticket = Ticket.objects.select_for_update().get(pk=ticket.pk)
                if ticket.creation_state == "complete":
                    return ticket
                if has_subform_rows(schema, ticket.form_data, only_unprepared=True):
                    prepare_initial_subforms(self, ticket, schema)
        materialize_subforms(self, ticket, schema, ticket.creator, initial=True)
        engine_required = workflow_version.process_definition_key or workflow_version.process_definition_id or workflow_version.flowable_deployment_id
        if engine_required or ticket.creation_state in {"starting", "bound"}:
            if not self.client:
                raise FlowableError(503, "流程引擎未配置，请恢复连接后重试")
            initial_start(self, ticket)
        return self._finish_creation(ticket.pk, ticket.form_data)

    def _definition_id(self, version: WorkflowVersion) -> str:
        if not version.process_definition_id:
            resolved = self.client.definition_for_deployment(version.flowable_deployment_id, version.process_definition_key)
            WorkflowVersion.objects.filter(pk=version.pk, process_definition_id="").update(process_definition_id=resolved)
            version.process_definition_id = resolved
        return version.process_definition_id

    @transaction.atomic
    def _finish_creation(self, ticket_id, form_data):
        ticket = Ticket.objects.select_for_update().get(pk=ticket_id)
        if ticket.creation_state == "complete":
            return ticket
        from apps.itsm.services.triggers import fire_triggers

        # 节点同步可能登记自动退回。节点、创建完成态和启动回执须一起提交。
        if ticket.process_instance_id:
            self.sync_ticket(ticket)
        ticket.form_data = form_data
        ticket.creation_state = "complete"
        ticket.save(update_fields=["form_data", "creation_state", "updated_at"])
        ticket.start_attempts.filter(kind="initial", state="bound").update(state="complete")
        fire_triggers(ticket, "create", ticket.creator)
        schedule_sync(ticket)
        return ticket

    def _assignee_variables(self, workflow_version: WorkflowVersion, creator: str, form_data: dict) -> dict:
        from apps.itsm.models import HandlerGroup

        group_ids = [
            node.get("assignee", {}).get("value")
            for node in (workflow_version.design or {}).get("nodes", [])
            if (node.get("assignee") or {}).get("source") == "handler_group"
        ]
        groups = (
            {row["id"]: row for row in HandlerGroup.objects.filter(domain=workflow_version.domain, id__in=group_ids).values("id", "members")}
            if group_ids
            else {}
        )
        resolver = AssigneeResolver(groups=groups)
        context = {"initiator": creator, "form": form_data}
        variables = {}
        for node in (workflow_version.design or {}).get("nodes") or []:
            if node.get("type") not in {"approval", "handle", "manual", "manual_trigger", "subprocess_handle"}:
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

    @transaction.atomic
    def sync_ticket(self, ticket: Ticket) -> None:
        ticket = Ticket.objects.select_for_update().get(pk=ticket.pk)
        from apps.itsm.services.ticket.manual_recovery import active_operations

        if not self.client or not ticket.process_instance_id or active_operations(ticket).exists():
            return
        try:
            items = self.client.list_tasks_including_children(ticket.process_instance_id)
        except FlowableError:
            raise
        seen = set()
        task_ids = [str(item.get("id") or "") for item in items]
        known_tasks = set(
            ticket.tasks.filter(flowable_task_id__in=task_ids, status__in=[TicketTask.TaskStatus.PENDING, TicketTask.TaskStatus.CLAIMED]).values_list(
                "flowable_task_id", flat=True
            )
        )
        active_nodes = {
            (str(item.get("processInstanceId") or ticket.process_instance_id), item.get("taskDefinitionKey") or task_id)
            for item, task_id in zip(items, task_ids)
            if task_id in known_tasks
        }
        current_tasks = [(str(item.get("assignee") or "").strip('"'), item.get("name") or "") for item in items]
        for item, task_id in zip(items, task_ids):
            seen.add(task_id)
            assignee = str(item.get("assignee") or "").strip('"')
            process_id = str(item.get("processInstanceId") or "")
            task, created = TicketTask.objects.get_or_create(
                ticket=ticket,
                flowable_task_id=task_id,
                defaults={
                    "node_id": item.get("taskDefinitionKey") or "",
                    "process_instance_id": process_id,
                    "node_name": item.get("name") or "",
                    "assignee": assignee,
                    "created_by": "system",
                    "updated_by": "system",
                },
            )
            if process_id and task.process_instance_id != process_id:
                task.process_instance_id = process_id
                task.save(update_fields=["process_instance_id", "updated_at"])
            if created:
                from apps.itsm.services.triggers import fire_triggers

                node_key = (process_id or ticket.process_instance_id, task.node_id or task_id)
                if node_key not in active_nodes:
                    active_nodes.add(node_key)
                    fire_triggers(ticket, "task_enter", "system", current_tasks=current_tasks)
                entered = _find_node(ticket.workflow_version.design if ticket.workflow_version_id else {}, node_id=task.node_id)
                if entered.get("enter_status"):
                    self._set_status(ticket, entered["enter_status"])
            if created and entered.get("auto_return") and not active_operations(ticket).exists():
                rule = entered["auto_return"] if isinstance(entered.get("auto_return"), dict) else {}
                current = (ticket.form_data or {}).get(rule.get("field"))
                if rule.get("field") and str(current) == str(rule.get("value")):
                    from apps.itsm.services.ticket.manual_recovery import advance, prepare

                    args = {"return_mode": "submit", "opinion": "自动退回"}
                    configured, args = self._validate_action(ticket, task, "return", args, "system", True, None, True)
                    operation = prepare(self, ticket, task, "return", args, "system", configured)
                    transaction.on_commit(lambda op=operation: advance(self, op), robust=True)
            if created and task.assignee:
                itsm_event.send(
                    sender=ticket,
                    event="task.created",
                    receivers=[task.assignee],
                    variables={
                        **ticket_notice_variables(ticket, link_to_ticket=True),
                        "title": ticket.title,
                        "node": task.node_name,
                    },
                    event_key=f"itsm-task-{task.flowable_task_id}",
                )
        ticket.tasks.filter(status__in=[TicketTask.TaskStatus.PENDING, TicketTask.TaskStatus.CLAIMED]).exclude(flowable_task_id__in=seen).update(
            status=TicketTask.TaskStatus.DONE
        )

        schedule_sync(ticket)

    def operate(
        self,
        ticket: Ticket,
        task: TicketTask,
        action: str,
        data: dict,
        operator: str,
        privileged: bool = False,
        *,
        expected_assignee: str | None = None,
        automatic_return: bool = False,
        handover_id: int | None = None,
    ) -> Ticket:
        if (
            action == "reopen"
            and ticket.workflow_version_id
            and (
                ticket.workflow_version.process_definition_key
                or ticket.workflow_version.process_definition_id
                or ticket.workflow_version.flowable_deployment_id
            )
        ):
            from apps.itsm.services.ticket.start_recovery import reopen_ticket

            return reopen_ticket(self, ticket, task, data, operator, privileged)
        from apps.itsm.services.ticket.manual_recovery import active_operations, advance, creates_child, prepare, requires_engine

        with transaction.atomic():
            ticket = Ticket.objects.select_for_update().get(pk=ticket.pk)
            if task is not None:
                task = ticket.tasks.select_for_update().get(pk=task.pk)
            if ticket.creation_state != "complete" or ticket.start_attempts.exclude(state="complete").exists():
                raise NodeActionValidationError("流程启动结果待核对，请稍后刷新")
            if handover_id:
                from apps.itsm.services.ticket.handover import RETRYABLE_RESULTS, _set_result

                if not _set_result(handover_id, task.pk, "unconfirmed", "结果待核对，请勿重复转交", RETRYABLE_RESULTS):
                    return ticket
            if active_operations(ticket).exists():
                raise NodeActionValidationError("该工单有待核对的引擎操作，请稍后刷新")
            node, data = self._validate_action(ticket, task, action, data, operator, privileged, expected_assignee, automatic_return)
            engine_action = requires_engine(ticket, task, action)
            if not engine_action and not creates_child(ticket, action, data):
                result = self._apply_action(ticket, task, action, data, operator, node)
                if handover_id:
                    _set_result(handover_id, task.pk, "succeeded", "交接成功", {"unconfirmed"})
                return result
            if engine_action and not self.client:
                raise FlowableError(503, "引擎绑定工单需要 Flowable 连接")
            operation = prepare(self, ticket, task, action, data, operator, node, handover_id=handover_id, local_parent=not engine_action)
        return advance(self, operation)

    def _validate_action(self, ticket, task, action, data, operator, privileged, expected_assignee, automatic_return):
        if expected_assignee is not None and (
            task is None or task.assignee != expected_assignee or task.status not in {TicketTask.TaskStatus.PENDING, TicketTask.TaskStatus.CLAIMED}
        ):
            raise TaskAssigneeChanged("原待办或处理人已变化")
        try:
            node = self._action_node(ticket, task, action, operator, privileged)
            design = ticket.workflow_version.design if ticket.workflow_version_id else {}
            required_opinions = (
                node_required_opinions(node, [action]) if action in TASK_ACTIONS else side_required_opinions(design, ticket.tasks.all(), [action])
            )
            if required_opinions or "opinion" in data:
                data = {**data, "opinion": validated_opinion(data.get("opinion", ""), bool(required_opinions))}
            if action == "transfer":
                if task is None:
                    raise ValueError("需要待办任务")
                target = require_transfer_target(transfer_users(ticket.domain, node), data.get("target"))
                data = {**data, "target": target}
        except (ValueError, PermissionError) as exc:
            if expected_assignee is not None:
                raise TransferRejected("待办暂时无法转交所选人员") from exc
            raise
        if action == "return":
            if task is None:
                raise NodeActionValidationError("需要待办任务")
            target = resolve_return_target(ticket, task, design, data, automatic=automatic_return)
            if self.client and ticket.process_instance_id and not automatic_return:
                runtime = self.client.list_tasks(ticket.process_instance_id)
                runtime_tasks = runtime.get("data") or []
                multi = (node.get("multi") or {}).get("mode") in {"any", "all", "serial"}
                if (
                    runtime.get("total", len(runtime_tasks)) != len(runtime_tasks)
                    or (len(runtime_tasks) > 1 and not multi)
                    or not any(row.get("id") == task.flowable_task_id for row in runtime_tasks)
                    or any(row.get("taskDefinitionKey") != task.node_id for row in runtime_tasks)
                ):
                    raise NodeActionValidationError("当前流程任务已变化，请刷新后回退")
            data = {**data, "return_node_id": target["node_id"], "return_node_name": target["name"]}
        return node, data

    def _apply_action(self, ticket, task, action, data, operator, node, *, saved_form=None):
        if action in {"suspend", "resume", "withdraw", "return", "transfer", "terminate", "close", "reopen", "urge", "save", "respond"}:
            return self._side_action(ticket, task, action, data, operator, node, saved_form=saved_form)
        if task is None:
            raise ValueError("需要待办任务")
        task.status = TicketTask.TaskStatus.CLAIMED if action == "claim" else TicketTask.TaskStatus.DONE
        task.assignee = operator
        task.save(update_fields=["status", "assignee", "updated_at"])
        if saved_form is None:
            self._save_form(ticket, node, data, task)
        else:
            ticket.form_data = saved_form
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
        if saved_form is not None and task.flowable_task_id and action != "claim" and ticket.status_id and ticket.status.key == "new":
            self._set_status(ticket, "processing")
        schedule_sync(ticket)
        return ticket

    def transfer_candidates(self, ticket, task, operator, privileged=False):
        node = self._action_node(ticket, task, "transfer", operator, privileged)
        return transfer_users(ticket.domain, node)

    def check_transfer_target(self, ticket, task, target, operator, privileged=False, *, opinion=""):
        node = self._action_node(ticket, task, "transfer", operator, privileged)
        validated_opinion(opinion, bool(node_required_opinions(node, ["transfer"])))
        require_transfer_target(transfer_users(ticket.domain, node), target)

    def _action_node(self, ticket, task, action, operator, privileged):
        self.authorize(ticket, task, action, operator, privileged)
        state = ticket.status.key if ticket.status_id else ""
        if state == "suspended" and action not in {"resume", "withdraw", "terminate", "close", "urge"}:
            raise ValueError("工单已挂起，请先恢复")
        if state in {"finished", "terminated", "cancelled"} and action != "reopen":
            raise ValueError("工单已结束，请先重新打开")
        if action == "resume" and state != "suspended":
            raise ValueError("只有挂起工单可以恢复")
        if action == "reopen" and state not in {"finished", "terminated", "cancelled"}:
            raise ValueError("只有已结束工单可以重新打开")
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
        design = ticket.workflow_version.design if ticket.workflow_version_id else {}
        node = _find_node(design, node_id=task.node_id) if task else {}
        if action == "submit" and node.get("type") == "approval":
            raise ValueError("审批节点只能通过或驳回")
        if action in {"approve", "reject"} and node.get("type") != "approval":
            raise ValueError("当前节点不是审批节点")
        if action not in TASK_ACTIONS and not side_action_enabled(design, list(ticket.tasks.all()), action):
            raise PermissionError("当前节点不允许此操作")
        if task and action in TASK_ACTIONS and action not in node_actions(node, task):
            raise PermissionError("当前节点不允许此操作")
        return node

    def authorize(self, ticket, task, action, operator, privileged=False):
        if not operator:
            raise PermissionError()
        if task is not None and task.status not in {"pending", "claimed"}:
            raise ValueError("任务已完成，请刷新")
        if privileged:
            return
        from apps.itsm.models.extend import TicketProxy

        principals = set(TicketProxy.objects.filter(domain=ticket.domain, agent=operator, is_enabled=True).values_list("principal", flat=True)) | {
            operator
        }
        if action in {"withdraw", "urge", "reopen"}:
            if ticket.creator not in principals:
                raise PermissionError()
        elif task is not None:
            if task.assignee not in principals:
                raise PermissionError()
        elif action == "save":
            raise PermissionError("保存必须指定当前任务")
        elif not ticket.tasks.filter(assignee__in=principals, status__in=["pending", "claimed"]).exists():
            raise PermissionError()

    def _validated_form(self, ticket, node, data, task=None):
        incoming = data.get("form_data") or {}
        if not isinstance(incoming, dict):
            raise ValueError("表单必须是对象")
        original = dict(ticket.form_data or {})
        schema = ticket_schema(ticket)
        if schema.get("fields"):
            cleaned = validate_submission(
                schema,
                incoming,
                self.identity,
                f"ticket:{ticket.id}",
                original=original,
                field_perm=_normalize_perm(node.get("field_perm")),
                receipt_context=task_fetch_context(ticket, task) if task else None,
            )
            return {**original, **cleaned}
        return {**original, **incoming}

    def _save_form(self, ticket, node, data, task=None):
        schema = ticket_schema(ticket)
        ticket.form_data = self._validated_form(ticket, node, data, task)
        from apps.itsm.services.ticket.subforms import materialize_subforms

        materialize_subforms(self, ticket, schema, ticket.updated_by or ticket.creator)
        ticket.save(update_fields=["form_data", "updated_at"])

    def _side_action(self, ticket: Ticket, task: TicketTask | None, action: str, data: dict, operator: str, node: dict, *, saved_form=None) -> Ticket:
        if action == "suspend":
            self._set_status(ticket, "suspended")
            pause(ticket)
        elif action == "resume":
            self._set_status(ticket, "processing")
            resume(ticket)
        elif action == "withdraw":
            self._set_status(ticket, "cancelled")
            ticket.tasks.filter(status__in=[TicketTask.TaskStatus.PENDING, TicketTask.TaskStatus.CLAIMED]).update(status=TicketTask.TaskStatus.DONE)
            finish_sla(ticket, "response")
            finish_sla(ticket, "resolve")
        elif action == "terminate":
            self._stop_process(ticket, "terminated")
        elif action == "close":
            self._stop_process(ticket, "finished", operator)
        elif action == "reopen":
            data = {**data, "round_started_at": timezone.now().isoformat()}
            self._reopen(ticket, operator)
        elif action == "urge":
            pending = list(
                ticket.tasks.filter(status__in=[TicketTask.TaskStatus.PENDING, TicketTask.TaskStatus.CLAIMED]).values_list("assignee", "node_name")
            )
            receivers = [assignee for assignee, _ in pending if assignee]
            dispatch_notification(
                "ticket.urge",
                {
                    **ticket_notice_variables(ticket, link_to_ticket=True),
                    "title": ticket.title,
                    "content": data.get("opinion") or "请尽快处理",
                    "node": "、".join(dict.fromkeys(name for _, name in pending if name)),
                },
                receivers or [ticket.creator],
                event_key=f"itsm-urge-{ticket.id}-{int(timezone.now().timestamp())}",
                site_only=ticket.is_test,
                domain=ticket.domain,
            )
        elif action == "respond":
            self._set_status(ticket, "processing")
        elif action == "save":
            if task is None:
                node = _find_node(ticket.workflow_version.design, node_type="submit")
            if saved_form is None:
                self._save_form(ticket, node, data, task)
            else:
                ticket.form_data = saved_form
                ticket.save(update_fields=["form_data", "updated_at"])
        elif action == "transfer":
            target = data["target"]
            task.assignee = target
            task.save(update_fields=["assignee", "updated_at"])
        elif action == "return":
            target_node = data["return_node_id"]
            design = ticket.workflow_version.design if ticket.workflow_version_id else {}
            target_status = "new" if _find_node(design, node_id=target_node).get("type") == "submit" else "processing"
            if not ticket.status_id or ticket.status.key != target_status:
                self._set_status(ticket, target_status)
            task.status = TicketTask.TaskStatus.DONE
            task.save(update_fields=["status", "updated_at"])
        self._log(ticket, task, action, data, operator)
        schedule_sync(ticket)
        return ticket

    def _reopen(self, ticket: Ticket, operator: str) -> None:
        self._set_status(ticket, "processing")
        version = ticket.workflow_version if ticket.workflow_version_id else None
        if not ticket.tasks.filter(status__in=["pending", "claimed"]).exists():
            TicketTask.objects.create(
                ticket=ticket,
                node_id=_find_node(version.design if version else {}, node_type="submit").get("id") or "submit",
                node_name=_find_node(version.design if version else {}, node_type="submit").get("name") or "提单",
                assignee=ticket.creator,
                created_by=operator,
                updated_by=operator,
            )

    def _stop_process(self, ticket: Ticket, status_key: str, operator: str | None = None) -> None:
        self._set_status(ticket, status_key, operator)
        ticket.tasks.filter(status__in=[TicketTask.TaskStatus.PENDING, TicketTask.TaskStatus.CLAIMED]).update(status=TicketTask.TaskStatus.DONE)
        finish_sla(ticket, "response")
        finish_sla(ticket, "resolve")

    def _status_target(self, ticket, target):
        status = target if isinstance(target, TicketStatus) else TicketStatus.objects.filter(key=target).first()
        if status is None:
            raise ValueError(f"缺少状态 {target}")
        if ticket.status_id != status.pk:
            allowed = StatusTransition.objects.filter(from_status_id=ticket.status_id)
            if allowed.exists() and not allowed.filter(to_status=status).exists():
                current = ticket.status.key if ticket.status_id else ""
                raise ValueError(f"不允许从 {current} 转到 {status.key}")
        return status

    def _set_status(self, ticket: Ticket, target: str | TicketStatus, operator: str | None = None, *, natural_end: bool = False) -> None:
        approved = getattr(ticket, "_approved_transition", None)
        status = approved if approved and target == approved.key else self._status_target(ticket, target)
        if ticket.status_id == status.pk:
            return
        key = status.key
        ticket.status = status
        ticket.finished_at = timezone.now() if key == "finished" else None
        ticket.save(update_fields=["status", "finished_at", "updated_at"])
        if key == "finished":
            from apps.itsm.services.triggers import fire_triggers

            actor = operator or ticket.updated_by or ticket.creator
            record_survey_invitation(ticket, actor)
            if natural_end:
                fire_triggers(ticket, "end", actor)
            fire_triggers(ticket, "finish", actor)

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

    def finish_if_ended(self, ticket: Ticket, operator: str | None = None) -> None:
        if ticket.status_id and ticket.status.key in {"finished", "terminated", "cancelled"}:
            return
        if ticket.process_instance_id:
            if not self.client:
                return
            try:
                historic = self.client._request("GET", f"/flowable-rest/service/history/historic-process-instances/{ticket.process_instance_id}")
            except FlowableError as exc:
                if exc.status == 404:
                    return
                raise
            if historic.get("id") != ticket.process_instance_id or not historic.get("endTime") or historic.get("deleteReason"):
                return
        with transaction.atomic():
            current = Ticket.objects.select_for_update().get(pk=ticket.pk)
            from apps.itsm.services.ticket.manual_recovery import active_operations

            if (
                active_operations(current).exists()
                or current.process_instance_id != ticket.process_instance_id
                or (current.status_id and current.status.key in {"finished", "terminated", "cancelled"})
            ):
                return
            if not TicketStatus.objects.filter(key="finished").exists():
                return
            self._set_status(current, "finished", operator, natural_end=bool(self.client and current.process_instance_id))
            finish_sla(current, "resolve")
            ticket.status, ticket.finished_at = current.status, current.finished_at


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


def workflow_schema(version) -> dict:
    snapshot = (version.design or {}).get("form_schema")
    if isinstance(snapshot, dict):
        return snapshot
    workflow = version.workflow
    if workflow.form_id and workflow.form.current_version_id:
        return workflow.form.current_version.schema or {"fields": []}
    return {"fields": []}


def ticket_schema(ticket) -> dict:
    if ticket.workflow_version_id:
        return workflow_schema(ticket.workflow_version)
    workflow = ticket.workflow
    if workflow.form_id and workflow.form.current_version_id:
        return workflow.form.current_version.schema or {"fields": []}
    return {"fields": []}
