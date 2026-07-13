# -- coding: utf-8 --
# @File: tasks.py
# @Time: 2025/3/3 15:34
# @Author: windyzhao
import os
from datetime import timedelta
from uuid import uuid4

from celery import shared_task
from django.utils.timezone import now

from apps.cmdb.collection.collect_tasks.job_collect import JobCollect
from apps.cmdb.collection.collect_tasks.protocol_collect import ProtocolCollect
from apps.cmdb.constants.constants import CollectPluginTypes, CollectRunStatusType
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.services.collect_dispatch_service import CollectDispatchService
from apps.cmdb.services.collect_tool_service import CollectToolService
from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService
from apps.cmdb.services.subscription_task import SubscriptionTaskService
from apps.core.logger import cmdb_logger as logger


def _is_unhelpful_error_message(message: str) -> bool:
    text = str(message or "").strip()
    return text in {"0", "1", "None", "null", "False", "True"}


def _build_exception_args_message(err: Exception) -> str:
    args = getattr(err, "args", ()) or ()
    if not args:
        return ""
    rendered = ", ".join(repr(arg) for arg in args)
    return f"{err.__class__.__name__}({rendered})"


def _build_safe_error_message(err: Exception) -> str:
    message = str(err).strip()
    if message and not _is_unhelpful_error_message(message):
        return message

    attr_message = getattr(err, "message", None)
    if isinstance(attr_message, str) and attr_message.strip():
        return attr_message.strip()

    detail = getattr(err, "detail", None)
    if isinstance(detail, str) and detail.strip():
        return detail.strip()

    args_message = _build_exception_args_message(err)
    if args_message:
        return args_message

    return err.__class__.__name__


def _build_traceback_excerpt(traceback_text: str, max_lines: int = 16) -> str:
    if not traceback_text:
        return ""
    lines = [line.rstrip() for line in str(traceback_text).splitlines() if line.strip()]
    if not lines:
        return ""
    return "\n".join(lines[-max_lines:])


def _build_traceback_location(traceback_text: str) -> str:
    if not traceback_text:
        return ""
    lines = [line.strip() for line in str(traceback_text).splitlines() if line.strip()]
    file_lines = [line for line in lines if line.startswith('File "')]
    return file_lines[-1] if file_lines else ""


def _claim_collect_task_execution(instance_id, start_time, execution_id=None):
    queryset = CollectModels._default_manager.filter(id=instance_id)
    execution_id = execution_id or str(uuid4())
    update_fields = {
        "exec_status": CollectRunStatusType.RUNNING,
        "exec_time": start_time,
        "task_id": execution_id,
    }
    updated = queryset.filter(exec_status=CollectRunStatusType.RUNNING, task_id=execution_id,).update(**update_fields)
    if not updated:
        updated = queryset.exclude(exec_status=CollectRunStatusType.RUNNING).update(**update_fields)
    if not updated:
        return None
    return CollectModels._default_manager.filter(id=instance_id).first()


def _save_collect_result_if_current(instance_id, execution_id, values):
    return bool(
        CollectModels._default_manager.filter(id=instance_id, task_id=execution_id, exec_status=CollectRunStatusType.RUNNING,).update(**values)
    )


def _resolve_execution_timeout_seconds(task):
    configured = (task.params or {}).get("task_job_timeout")
    for value in (configured, os.getenv("TASK_JOB_TIMEOUT"), 600):
        try:
            timeout_seconds = int(value)
        except (TypeError, ValueError):
            continue
        if timeout_seconds > 0:
            return timeout_seconds
    return 600


def _timeout_collect_task_if_current(task, checked_at):
    if not task.exec_time:
        return False
    deadline_seconds = _resolve_execution_timeout_seconds(task)
    if checked_at <= task.exec_time + timedelta(seconds=deadline_seconds):
        return False

    collect_digest = {
        "message": "采集执行已超过 deadline，状态置为超时",
        "execution_id": task.task_id,
        "deadline_seconds": deadline_seconds,
        "started_at": task.exec_time.isoformat(),
    }
    return bool(
        CollectModels._default_manager.filter(
            id=task.id, task_id=task.task_id, exec_status=CollectRunStatusType.RUNNING, exec_time=task.exec_time,
        ).update(
            exec_status=CollectRunStatusType.TIME_OUT, collect_digest=collect_digest, updated_at=checked_at,
        )
    )


@shared_task
def sync_collect_task(instance_id, execution_id=None):
    """
    同步采集任务
    """
    logger.info("[CollectTask] 开始采集任务 task_id=%s", instance_id)
    start_time = now()
    instance = _claim_collect_task_execution(instance_id, start_time, execution_id=execution_id)
    if not instance:
        exists = CollectModels._default_manager.filter(id=instance_id).exists()
        if exists:
            logger.info("[CollectTask] 采集任务已在执行中，跳过重复执行 task_id=%s", instance_id)
        else:
            logger.warning("[CollectTask] 采集任务不存在，跳过执行 task_id=%s", instance_id)
        return
    execution_id = instance.task_id
    from apps.cmdb.services.collect_service import CollectModelService

    CollectModelService.repair_host_cloud_snapshot(instance)
    exec_error_message = ""
    exec_traceback_excerpt = ""
    exec_traceback_location = ""
    task_exec_status = CollectRunStatusType.SUCCESS
    config_file_pending = False
    try:
        if CollectDispatchService.should_dispatch(instance):
            result, format_data = CollectDispatchService.execute_task(instance)
        else:
            if instance.is_job:
                collect = JobCollect(task=instance)
                result, format_data = collect.main()
            else:
                collect = ProtocolCollect(task=instance)
                result, format_data = collect.main()

        config_file_pending = instance.task_type == CollectPluginTypes.CONFIG_FILE and (result.get("config_file") or {}).get("status") == "pending"
        if config_file_pending:
            instance.exec_status = CollectRunStatusType.RUNNING
        else:
            instance.exec_status = CollectRunStatusType.SUCCESS

    except Exception as err:
        import traceback

        traceback_text = traceback.format_exc()
        logger.error(
            "[CollectTask] 同步采集数据失败 task_id=%s, error=%s", instance_id, traceback_text,
        )
        exec_error_message = "采集任务执行失败（task_id={}）：{}".format(instance_id, _build_safe_error_message(err))
        exec_traceback_excerpt = _build_traceback_excerpt(traceback_text)
        exec_traceback_location = _build_traceback_location(traceback_text)
        if exec_traceback_location:
            exec_error_message = f"{exec_error_message} @ {exec_traceback_location}"
        result = {}
        format_data = {}
        instance.exec_status = CollectRunStatusType.ERROR
        task_exec_status = CollectRunStatusType.ERROR

    try:
        instance.collect_data = result
        instance.format_data = format_data
        collect_digest = {
            "add": len(format_data.get("add", [])),
            "add_error": len([i for i in format_data.get("add", []) if i.get("_status") != "success"]),
            "update": len(format_data.get("update", [])),
            "update_error": len([i for i in format_data.get("update", []) if i.get("_status") != "success"]),
            "delete": len(format_data.get("delete", [])),
            "delete_error": len([i for i in format_data.get("delete", []) if i.get("_status") != "success"]),
            "association": len(format_data.get("association", [])),
            "association_error": len([i for i in format_data.get("association", []) if i.get("_status") != "success"]),
            "all": format_data.get("all", 0),  # 总数是发现的正常数据总数，例如：扫描了10个ip，其中6个是真的ip，4个ip不存在，总数为6
        }
        # add是需要新增的数据，add_success是实际新增成功的数据（实际到cmdb的数据），add_error是新增失败的数据，其他以此类推
        collect_digest["add_success"] = collect_digest["add"] - collect_digest["add_error"]
        collect_digest["update_success"] = collect_digest["update"] - collect_digest["update_error"]
        collect_digest["delete_success"] = collect_digest["delete"] - collect_digest["delete_error"]
        collect_digest["association_success"] = collect_digest["association"] - collect_digest["association_error"]
        # 如果任务执行失败，添加错误信息提示
        if task_exec_status == CollectRunStatusType.ERROR:
            collect_digest["message"] = exec_error_message
            if exec_traceback_excerpt:
                collect_digest["traceback"] = exec_traceback_excerpt
        elif config_file_pending:
            collect_digest["message"] = "配置文件采集已触发，等待回传中"
        elif format_data.get("__raw_data__", []).__len__() == 0:
            collect_digest["message"] = "未发现任何有效数据，请检查采集目标连通性、凭据与采集范围配置"
            instance.exec_status = CollectRunStatusType.ERROR
        else:
            # 计算最后数据的最后上报时间
            last_time = ""
            for i in format_data["__raw_data__"]:
                if i.get("__time__"):
                    if i["__time__"] > last_time:
                        last_time = i["__time__"]
            collect_digest["last_time"] = last_time

            # 任务状态判定以"整体成败"为口径，而非单个操作类型是否全挂：
            # - 实例数据(add/update/delete)有要写、但成功 0 条 → ERROR（写库整体失败，最危险）
            # - 否则只要存在任意失败(含 association) → PARTIAL_SUCCESS（部分成功，需运维感知）
            # - 全部成功 → 保持 SUCCESS
            # 注：association 失败不单独升级为 ERROR（目标实例未采到等场景常见且非致命）。
            data_keys = ("add", "update", "delete")
            data_total = sum(collect_digest.get(k, 0) for k in data_keys)
            data_error = sum(collect_digest.get(f"{k}_error", 0) for k in data_keys)
            data_success = data_total - data_error
            any_failure = any(collect_digest.get(f"{k}_error", 0) > 0 for k in ("add", "update", "delete", "association"))
            if data_total > 0 and data_success == 0:
                instance.exec_status = CollectRunStatusType.ERROR
                collect_digest["message"] = "实例数据写入全部失败，请检查 add/update/delete 错误数"
            elif any_failure:
                instance.exec_status = CollectRunStatusType.PARTIAL_SUCCESS
                collect_digest["message"] = "部分数据写入失败，请检查 add/update/delete/association 错误数"
        update_values = {
            "collect_data": result,
            "format_data": format_data,
            "collect_digest": collect_digest,
            "exec_status": instance.exec_status,
            "updated_at": now(),
        }
        updated = _save_collect_result_if_current(instance_id, execution_id, update_values,)
        if not updated:
            logger.info(
                "[CollectTask] 忽略旧执行结果 stale_execution_result " "task_id=%s, execution_id=%s", instance_id, execution_id,
            )
    except Exception as err:
        import traceback

        logger.error(
            "[CollectTask] 保存采集结果失败 task_id=%s, error=%s", instance_id, traceback.format_exc(),
        )
        _save_collect_result_if_current(
            instance_id,
            execution_id,
            {
                "exec_status": CollectRunStatusType.ERROR,
                "collect_digest": {"message": "采集结果写入失败（task_id={}）：{}".format(instance_id, _build_safe_error_message(err),)},
                "updated_at": now(),
            },
        )

    logger.info("[CollectTask] 采集任务执行结束 task_id=%s", instance_id)


@shared_task
def sync_periodic_update_task_status():
    """按每次 execution 的 deadline 收敛超时状态。"""
    checked_at = now()
    logger.info("[CollectTask] 开始周期巡检超时采集任务")
    timeout_count = 0
    tasks = (
        CollectModels._default_manager.filter(exec_status=CollectRunStatusType.RUNNING,)
        .only("id", "task_id", "exec_status", "exec_time", "params")
        .iterator(chunk_size=200)
    )
    for task in tasks:
        timeout_count += int(_timeout_collect_task_if_current(task, checked_at))
    logger.info(
        "[CollectTask] 周期巡检超时采集任务完成，超时任务数 rows=%s", timeout_count,
    )


@shared_task
def sync_collect_credential_results_task():
    logger.info("Skip legacy credential pull task because CMDB now receives Stargazer pushes via NATS")
    return {
        "result": True,
        "skipped": True,
        "message": "collect credential results are received via NATS push",
    }


@shared_task
def sync_cmdb_display_fields_task(data: dict):
    """
    同步 CMDB 实例的 _display 字段（Celery 任务）

    当系统管理模块修改组织或用户信息时，触发此任务同步更新 CMDB 所有实例的 _display 字段

    Args:
        data: 变更数据字典
            格式: {
                "organizations": [{"id": 1, "name": "新组织名"}],
                "users": [{"id": 1, "display_name": "新显示名"}]
            }

    Returns:
        dict: 执行结果
            格式: {
                "result": True,
                "data": {"organizations": 10, "users": 5}
            }
    """
    try:
        from apps.cmdb.display_field import DisplayFieldSynchronizer

        logger.info(f"[SyncCMDBDisplayFields] 开始同步 CMDB _display 字段, 组织数: {len(data.get('organizations', []))}, 用户数: {len(data.get('users', []))}")

        # 执行同步
        result = DisplayFieldSynchronizer.sync_all(data)

        logger.info(f"[SyncCMDBDisplayFields] 同步完成, 组织更新实例数: {result.get('organizations', 0)}, 用户更新实例数: {result.get('users', 0)}")

        return {
            "result": True,
            "message": "CMDB display fields synced successfully",
            "data": result,
        }

    except Exception as exc:
        logger.error(f"[SyncCMDBDisplayFields] 同步失败: {str(exc)}", exc_info=True)
        return {
            "result": False,
            "message": f"Failed to sync CMDB display fields: {str(exc)}",
        }


@shared_task
def execute_collect_tool_debug_task(debug_id: str, payload: dict, service_name: str, timeout: int):
    logger.info(f"开始执行采集工具调试任务 debug_id={debug_id}, action={payload.get('action')}")
    try:
        return CollectToolService.run_debug_task(debug_id, payload, service_name, timeout)
    except Exception as exc:
        logger.error(f"采集工具调试任务失败 debug_id={debug_id}, error={exc}", exc_info=True)
        result = CollectToolService.build_error_result(
            debug_id=debug_id, payload=payload, stage="unknown", summary=f"调试任务执行失败: {exc}", raw_log=str(exc),
        )
        CollectToolService.save_debug_state(debug_id, "error", result)
        return result


@shared_task
def sync_public_enum_library_snapshots_task(library_id: str, trigger: str, operator: str | None = None) -> dict:
    from apps.cmdb.services.public_enum_library import sync_library_snapshots

    logger.info(f"[SyncPublicEnumSnapshots] task started library_id={library_id}, trigger={trigger}, operator={operator}")
    return sync_library_snapshots(library_id, trigger, operator)


@shared_task
def check_subscription_rules() -> None:
    SubscriptionTaskService.check_rules()


@shared_task
def send_subscription_notifications(delivery_ids: list[int] | None = None,) -> None:
    SubscriptionTaskService.send_notifications(delivery_ids=delivery_ids)


@shared_task
def daily_data_cleanup_task() -> dict:
    from apps.cmdb.services.data_cleanup_service import DataCleanupService

    logger.info("[DataCleanup] 启动每日过期数据清理任务")
    return DataCleanupService.run_daily_cleanup()


@shared_task
def reconcile_instance_auto_association_task(instance_id: int) -> dict:
    from apps.cmdb.services.auto_relation_reconcile import AutoRelationRuleReconcileService

    logger.info("[AutoRelationRule] start instance reconcile, instance_id=%s", instance_id)
    return AutoRelationRuleReconcileService.reconcile_for_instance(instance_id)


@shared_task
def full_sync_auto_association_rule_task(model_asst_id: str) -> dict:
    from apps.cmdb.services.auto_relation_reconcile import AutoRelationRuleReconcileService

    logger.info("[AutoRelationRule] start rule full sync, model_asst_id=%s", model_asst_id)
    return AutoRelationRuleReconcileService.full_sync_rule(model_asst_id)


@shared_task
def sync_node_mgmt_hosts() -> dict:
    logger.info("[NodeMgmtSync] 开始同步节点管理主机信息")
    try:
        data = NodeMgmtSyncService.trigger_sync()
    except Exception:
        logger.exception("[NodeMgmtSync] 同步节点管理主机信息失败")
        raise
    logger.info("[NodeMgmtSync] 同步节点管理主机信息完成")
    return data


@shared_task
def collect_node_mgmt_hosts():
    logger.info("[NodeMgmtSync] 开始采集节点管理主机信息")
    try:
        NodeMgmtSyncService.trigger_collect()
    except Exception:
        logger.exception("[NodeMgmtSync] 采集节点管理主机信息失败")
        raise
    logger.info("[NodeMgmtSync] 采集节点管理主机信息结束")


@shared_task
def reconcile_ipam_task() -> dict:
    """IPAM 与 CMDB 自动对账周期任务。规格 §5.5。"""
    from apps.cmdb.services.ipam_reconcile import run_reconciliation

    logger.info("[IPAM] 开始对账...")
    result = run_reconciliation()
    logger.info(f"[IPAM] 对账完成: {result}")
    return result


@shared_task
def reconcile_config_file_content_task() -> dict:
    from apps.cmdb.services.config_file_content_lifecycle import ConfigFileContentLifecycle

    recovery = ConfigFileContentLifecycle.recover_stale()
    orphans_deleted = ConfigFileContentLifecycle.cleanup_orphan_temp_objects()
    result = {**recovery, "orphans_deleted": orphans_deleted}
    logger.info("[ConfigFileContent] 周期补偿完成: %s", result)
    return result
