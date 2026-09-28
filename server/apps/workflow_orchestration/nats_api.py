from __future__ import annotations

import nats_client
from apps.core.logger import workflow_orchestration_logger as logger
from apps.workflow_orchestration.services.definitions import DefinitionValidationError
from apps.workflow_orchestration.services.nats_triggers import invoke_nats_trigger
from apps.workflow_orchestration.services.triggers import TriggerConflict


@nats_client.register
def trigger_orchestration_workflow_by_nats(data, actor_context):
    """Internal NATS RPC adapter; caller identity and organization scope are mandatory."""
    try:
        execution, created = invoke_nats_trigger(
            data,
            actor_context,
            message_subject=str(data.get("subject") or "") if isinstance(data, dict) else "",
        )
    except (DefinitionValidationError, TriggerConflict) as error:
        return {"result": False, "message": str(error)}
    except Exception as error:
        safe_error = RuntimeError("workflow NATS trigger failed")
        logger.error(
            "event=workflow_nats_trigger_failed failed_stage=invoke error_type=%s",
            type(error).__name__,
            exc_info=(type(safe_error), safe_error, error.__traceback__),
        )
        return {"result": False, "message": "编排服务暂不可用"}
    return {"result": True, "data": {"execution_id": str(execution.pk), "created": created}}
