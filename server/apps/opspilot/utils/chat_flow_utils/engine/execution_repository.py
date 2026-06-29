"""
Workflow execution persistence repository.

This module owns the ORM writes for ChatFlowEngine execution state so the
engine can stay focused on orchestration and protocol handling.
"""

import json
from datetime import datetime
from datetime import timezone as dt_timezone
from typing import Any, Callable, Dict, Optional

from django.utils import timezone

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.enum import WorkFlowTaskStatus
from apps.opspilot.models import BotWorkFlow
from apps.opspilot.models.bot_mgmt import (
    WorkFlowConversationHistory,
    WorkFlowTaskNodeResult,
    WorkFlowTaskResult,
)

from .core.models import NodeExecutionContext


EXECUTION_RESULT_UPDATE_FIELDS = ["status", "input_data", "output_data", "last_output", "execute_type", "finished_at"]


class ExecutionRepository:
    """Persistence boundary for workflow execution records."""

    def __init__(self, instance: BotWorkFlow, execution_id: str):
        self.instance = instance
        self.execution_id = execution_id

    @staticmethod
    def to_datetime(timestamp: Optional[float]):
        if not timestamp:
            return None
        return datetime.fromtimestamp(timestamp, tz=dt_timezone.utc)

    def ensure_result_started(
        self,
        input_data: Dict[str, Any],
        start_node_type: str,
        task_result: Optional[WorkFlowTaskResult],
        is_test: bool,
        get_execute_type: Callable[[Optional[str]], str],
    ) -> WorkFlowTaskResult:
        """Ensure the main execution record exists."""
        if task_result:
            return task_result

        task_result = (
            WorkFlowTaskResult.objects.filter(bot_work_flow=self.instance, execution_id=self.execution_id)
            .order_by("-id")
            .first()
        )
        if task_result:
            return task_result

        return WorkFlowTaskResult.objects.create(
            bot_work_flow=self.instance,
            execution_id=self.execution_id,
            status=WorkFlowTaskStatus.RUNNING,
            input_data=json.dumps(input_data, ensure_ascii=False),
            output_data={},
            execute_type=get_execute_type(start_node_type),
            is_test=is_test,
        )

    def record_node_result(
        self,
        node_id: str,
        context: NodeExecutionContext,
        node_index: Optional[int],
        node_type: str,
        node_name: str,
        task_result: Optional[WorkFlowTaskResult],
    ) -> None:
        """Persist node execution detail with idempotent upsert."""
        if not node_id or not context:
            return

        try:
            status = context.status.value if hasattr(context.status, "value") else str(context.status)

            duration_ms = None
            if context.start_time and context.end_time:
                duration_ms = int((context.end_time - context.start_time) * 1000)

            defaults = {
                "node_name": node_name,
                "node_type": node_type,
                "node_index": node_index,
                "status": status,
                "input_data": context.input_data or {},
                "output_data": context.output_data or {},
                "error_message": context.error_message,
                "start_time": self.to_datetime(context.start_time),
                "end_time": self.to_datetime(context.end_time),
                "duration_ms": duration_ms,
            }
            if task_result:
                defaults["task_result"] = task_result

            WorkFlowTaskNodeResult.objects.update_or_create(
                execution_id=self.execution_id,
                node_id=node_id,
                defaults=defaults,
            )
        except Exception as e:
            logger.exception(
                f"记录节点执行明细失败: execution_id={self.execution_id}, node_id={node_id}, error={str(e)}"
            )

    def record_execution_result(
        self,
        input_data: Dict[str, Any],
        result: Any,
        success: bool,
        start_node_type: str,
        task_result: Optional[WorkFlowTaskResult],
        is_test: bool,
        get_execute_type: Callable[[Optional[str]], str],
        build_output_data: Callable[[], Dict[str, Any]],
    ) -> Optional[WorkFlowTaskResult]:
        """Persist final workflow execution result."""
        try:
            task_result = self.ensure_result_started(
                input_data,
                start_node_type,
                task_result,
                is_test,
                get_execute_type,
            )
            interrupted = isinstance(result, dict) and result.get("interrupted")
            if task_result.status == WorkFlowTaskStatus.INTERRUPTED and not interrupted:
                logger.info("跳过执行结果覆盖，执行已中断: execution_id=%s", self.execution_id)
                return task_result

            output_data = build_output_data()
            status = (
                WorkFlowTaskStatus.INTERRUPTED
                if interrupted
                else (WorkFlowTaskStatus.SUCCESS if success else WorkFlowTaskStatus.FAIL)
            )
            input_data_str = json.dumps(input_data, ensure_ascii=False)

            if isinstance(result, dict):
                last_output = json.dumps(result, ensure_ascii=False)
            elif isinstance(result, str):
                last_output = result
            else:
                last_output = str(result)

            task_result.status = status
            task_result.input_data = input_data_str
            task_result.output_data = output_data
            task_result.last_output = last_output
            task_result.execute_type = get_execute_type(start_node_type)
            task_result.finished_at = timezone.now()
            task_result.save(update_fields=EXECUTION_RESULT_UPDATE_FIELDS)

            WorkFlowTaskNodeResult.objects.filter(
                execution_id=self.execution_id,
                task_result__isnull=True,
            ).update(task_result=task_result)
            return task_result

        except Exception as e:
            logger.exception(
                f"记录工作流执行结果失败: execution_id={self.execution_id}, success={success}, error={str(e)}"
            )
            return task_result

    def finalize_interrupted_execution(
        self,
        task_result: WorkFlowTaskResult,
        input_data: Dict[str, Any],
        output_data: Dict[str, Any],
        result: Any,
        execute_type: str,
    ) -> None:
        """Mark an execution as interrupted and attach pending node results."""
        if isinstance(result, dict):
            last_output = json.dumps(result, ensure_ascii=False)
        elif isinstance(result, str):
            last_output = result
        else:
            last_output = str(result or "execution interrupted")

        task_result.status = WorkFlowTaskStatus.INTERRUPTED
        task_result.input_data = json.dumps(input_data, ensure_ascii=False)
        task_result.output_data = output_data
        task_result.last_output = last_output
        task_result.execute_type = execute_type
        task_result.finished_at = timezone.now()
        task_result.save(update_fields=EXECUTION_RESULT_UPDATE_FIELDS)

        WorkFlowTaskNodeResult.objects.filter(
            execution_id=self.execution_id,
            task_result__isnull=True,
        ).update(task_result=task_result)

    def record_conversation_history(
        self,
        user_id: str,
        message: Any,
        role: str,
        entry_type: str,
        node_id: str = "",
        session_id: str = "",
    ) -> None:
        """Persist workflow conversation history."""
        if not user_id or not message or entry_type == "celery":
            return

        try:
            if isinstance(message, dict):
                content = json.dumps(message, ensure_ascii=False)
            elif isinstance(message, str):
                content = message
            else:
                content = str(message)

            WorkFlowConversationHistory.objects.create(
                bot_id=self.instance.bot_id,
                node_id=node_id,
                user_id=user_id,
                conversation_role=role,
                conversation_content=content,
                conversation_time=timezone.now(),
                entry_type=entry_type,
                session_id=session_id,
                execution_id=self.execution_id,
            )
        except Exception as e:
            logger.exception(
                f"记录{role}对话历史失败: execution_id={self.execution_id}, user_id={user_id}, error={str(e)}"
            )
