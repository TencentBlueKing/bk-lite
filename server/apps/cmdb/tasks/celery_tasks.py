# -- coding: utf-8 --
# @File: tasks.py
# @Time: 2025/3/3 15:34
# @Author: windyzhao
from datetime import timedelta

from celery import shared_task
from django.utils.timezone import now

from apps.cmdb.collection.collect_tasks.job_collect import JobCollect
from apps.cmdb.collection.collect_tasks.protocol_collect import ProtocolCollect
from apps.cmdb.constants.constants import CollectPluginTypes, CollectRunStatusType
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.services.collect_dispatch_service import CollectDispatchService
from apps.cmdb.services.collect_tool_service import CollectToolService
from apps.cmdb.services.subscription_task import SubscriptionTaskService
from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService
from apps.core.logger import cmdb_logger as logger


def _build_safe_error_message(err: Exception) -> str:
    message = str(err).strip()
    if message:
        return message

    attr_message = getattr(err, "message", None)
    if isinstance(attr_message, str) and attr_message.strip():
        return attr_message.strip()

    detail = getattr(err, "detail", None)
    if isinstance(detail, str) and detail.strip():
        return detail.strip()

    return err.__class__.__name__


@shared_task
def sync_collect_task(instance_id):
    """
    同步采集任务
    """
    logger.info("开始采集任务 task_id={}".format(instance_id))
    instance = CollectModels._default_manager.filter(id=instance_id).first()
    if not instance:
        return
    from apps.cmdb.services.collect_service import CollectModelService

    CollectModelService.repair_host_cloud_snapshot(instance)
    if instance.exec_status == CollectRunStatusType.NOT_START:
        CollectModels._default_manager.filter(id=instance_id).update(exec_status=CollectRunStatusType.RUNNING)
    # 防止周期触发与延迟补跑重叠导致同一任务并发执行
    # if instance.exec_status == CollectRunStatusType.RUNNING:
    #     logger.info("采集任务已在执行中，跳过重复执行 task_id={}".format(instance_id))
    #     return
    # 统一在 Celery 执行入口更新任务开始时间和运行状态
    start_time = now()
    instance.exec_status = CollectRunStatusType.RUNNING
    instance.exec_time = start_time
    CollectModels._default_manager.filter(id=instance_id).update(
        exec_status=CollectRunStatusType.RUNNING,
        exec_time=start_time,
    )
    exec_error_message = ""
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

        config_file_pending = (
            instance.task_type == CollectPluginTypes.CONFIG_FILE
            and (result.get("config_file") or {}).get("status") == "pending"
        )
        if config_file_pending:
            instance.exec_status = CollectRunStatusType.RUNNING
        else:
            instance.exec_status = CollectRunStatusType.SUCCESS

    except Exception as err:
        import traceback

        logger.error("同步数据失败 task_id={}, error={}".format(instance_id, traceback.format_exc()))
        exec_error_message = "同步数据失败, error={}".format(_build_safe_error_message(err))
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
        elif config_file_pending:
            collect_digest["message"] = "配置文件采集已触发，等待回传中"
        elif format_data.get("__raw_data__", []).__len__() == 0:
            collect_digest["message"] = "没有发现任何有效数据!"
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
            any_failure = any(
                collect_digest.get(f"{k}_error", 0) > 0 for k in ("add", "update", "delete", "association")
            )
            if data_total > 0 and data_success == 0:
                instance.exec_status = CollectRunStatusType.ERROR
                collect_digest["message"] = "实例数据写入全部失败，请检查 add/update/delete 错误数"
            elif any_failure:
                instance.exec_status = CollectRunStatusType.PARTIAL_SUCCESS
                collect_digest["message"] = "部分数据写入失败，请检查 add/update/delete/association 错误数"
        instance.collect_digest = collect_digest
        if config_file_pending:
            updated = CollectModels._default_manager.filter(id=instance_id, collect_data={}).update(
                collect_data=result,
                format_data=format_data,
                collect_digest=collect_digest,
                updated_at=now(),
            )
            if not updated:
                logger.info("配置文件采集结果已由回调更新，跳过本地 pending 覆盖 task_id=%s", instance_id)
        else:
            # topology_snapshot 由采集插件在运行中途直接 update，刷新避免被本次 save 覆盖
            instance.refresh_from_db(fields=["topology_snapshot"])
            instance.save()
    except Exception as err:
        import traceback

        logger.error("保存采集结果失败 task_id={}, error={}".format(instance_id, traceback.format_exc()))
        CollectModels._default_manager.filter(id=instance_id).update(
            exec_status=CollectRunStatusType.ERROR,
            collect_digest={"message": "保存采集结果失败: {}".format(err)},
        )

    logger.info("采集任务执行结束 task_id={}".format(instance_id))


@shared_task
def sync_periodic_update_task_status():
    """
    执行脚本5分钟更新一次脚本结果
    :param :
    :return:
    """
    logger.info("==开始周期执行修改采集状态==")
    five_minutes_ago = now() - timedelta(minutes=5)
    config_file_rows = CollectModels._default_manager.filter(
        task_type=CollectPluginTypes.CONFIG_FILE,
        exec_status=CollectRunStatusType.RUNNING,
        exec_time__lt=five_minutes_ago,
    ).update(
        exec_status=CollectRunStatusType.ERROR,
        collect_digest={"message": "配置文件采集已触发，但在 5 分钟内未收到回传结果"},
    )
    rows = CollectModels._default_manager.filter(
        exec_status=CollectRunStatusType.RUNNING,
        exec_time__lt=five_minutes_ago,
    ).exclude(task_type=CollectPluginTypes.CONFIG_FILE).update(
        exec_status=CollectRunStatusType.ERROR
    )
    logger.info("开始周期执行修改采集状态完成, rows={}, config_file_rows={}".format(rows, config_file_rows))


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
            debug_id=debug_id,
            payload=payload,
            stage="unknown",
            summary=f"调试任务执行失败: {exc}",
            raw_log=str(exc),
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
def send_subscription_notifications(
    event_groups: list[dict] | None = None,
) -> None:
    SubscriptionTaskService.send_notifications(event_groups=event_groups)


@shared_task
def daily_data_cleanup_task() -> dict:
    from apps.cmdb.services.data_cleanup_service import DataCleanupService

    logger.info("Starting daily data cleanup task")
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
    logger.info("==开始同步节点管理主机信息==")
    try:
        data = NodeMgmtSyncService.trigger_sync()
    except Exception:
        logger.exception("==同步节点管理主机信息失败==")
        raise
    logger.info("==同步节点管理主机信息完成==")
    return data


@shared_task
def collect_node_mgmt_hosts():
    logger.info("==开始采集节点管理主机信息==")
    try:
        NodeMgmtSyncService.trigger_collect()
    except Exception:
        logger.exception("==采集节点管理主机信息失败==")
        raise
    logger.info("==采集采集节点管理主机信息结束==")

