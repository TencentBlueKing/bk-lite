"""将已发布流程的 NATS 触发器投影为系统管理托管通道。

通道只是告警中心等平台应用的统一入口；组织边界、触发器状态、
标准事件信封和幂等执行仍由编排中心校验。
"""

from apps.core.logger import workflow_orchestration_logger as logger
from apps.rpc.system_mgmt import SystemMgmt
from apps.workflow_orchestration.models import Workflow, WorkflowTrigger


def sync_workflow_nats_channels(workflow_id: int) -> dict:
    """对账单个流程的 NATS 托管通道；失败不回滚已完成的发布或启停。"""
    workflow = Workflow.all_objects.filter(pk=workflow_id).first()
    if workflow is None or workflow.deleted_at is not None:
        return delete_workflow_nats_channels(workflow_id)

    triggers = workflow.triggers.filter(trigger_type=WorkflowTrigger.Type.NATS).order_by("node_key")
    nodes = [
        {
            "trigger_id": str(trigger.pk),
            "node_key": trigger.node_key,
            "name": trigger.name,
            "subject": str((trigger.config or {}).get("subject") or ""),
        }
        for trigger in triggers
    ]
    try:
        result = SystemMgmt().sync_workflow_orchestration_nats_channels(
            workflow_id=workflow.pk,
            workflow_name=workflow.name,
            team=workflow.team,
            nodes=nodes,
            active=bool(workflow.enabled and workflow.status == Workflow.Status.PUBLISHED),
        )
    except Exception as error:  # noqa: BLE001 - RPC 失败不得阻断流程生命周期
        safe_error = RuntimeError("workflow managed NATS channel sync failed")
        logger.error(
            "event=workflow_managed_nats_sync_failed workflow_id=%s failed_stage=system_mgmt_rpc error_type=%s",
            workflow_id,
            type(error).__name__,
            exc_info=(type(safe_error), safe_error, error.__traceback__),
        )
        return {"result": False, "message": "托管 NATS 通道同步失败"}
    if not isinstance(result, dict) or result.get("result") is False:
        logger.warning(
            "event=workflow_managed_nats_sync_rejected workflow_id=%s failed_stage=system_mgmt_rpc error_type=DownstreamRejected",
            workflow_id,
        )
        return result if isinstance(result, dict) else {"result": False, "message": "托管 NATS 通道同步失败"}
    return result


def delete_workflow_nats_channels(workflow_id: int) -> dict:
    """删除单个流程的全部托管 NATS 通道。"""
    try:
        result = SystemMgmt().delete_workflow_orchestration_nats_channels(workflow_id=workflow_id)
    except Exception as error:  # noqa: BLE001 - 软删除结果不得被外部清理失败覆盖
        safe_error = RuntimeError("workflow managed NATS channel cleanup failed")
        logger.error(
            "event=workflow_managed_nats_cleanup_failed workflow_id=%s failed_stage=system_mgmt_rpc error_type=%s",
            workflow_id,
            type(error).__name__,
            exc_info=(type(safe_error), safe_error, error.__traceback__),
        )
        return {"result": False, "message": "托管 NATS 通道清理失败"}
    return result if isinstance(result, dict) else {"result": False, "message": "托管 NATS 通道清理失败"}
