"""Job Management NATS API - 用于数据权限规则"""

from asgiref.sync import async_to_sync
from django.utils import timezone

import nats_client
from apps.core.logger import job_logger as logger
from apps.job_mgmt.constants import ExecutionStatus
from apps.job_mgmt.models import DangerousPath, DangerousRule, JobExecution, Playbook, ScheduledTask, Script, Target
from apps.node_mgmt.utils.s3 import delete_s3_file


@nats_client.register
def get_job_mgmt_module_list():
    """获取作业管理模块列表"""
    return [
        {"name": "script", "display_name": "脚本库"},
        {"name": "playbook", "display_name": "Playbook库"},
        {"name": "target", "display_name": "目标"},
        {"name": "job_execution", "display_name": "作业执行"},
        {"name": "scheduled_task", "display_name": "定时任务"},
        {
            "name": "system",
            "display_name": "系统管理",
            "children": [
                {"name": "dangerous_rule", "display_name": "高危命令"},
                {"name": "dangerous_path", "display_name": "高危路径"},
            ],
        },
    ]


@nats_client.register
def get_job_mgmt_module_data(module, child_module, page, page_size, group_id):
    """获取作业管理模块数据"""
    model_map = {
        "script": Script,
        "playbook": Playbook,
        "target": Target,
        "job_execution": JobExecution,
        "scheduled_task": ScheduledTask,
    }
    system_model_map = {
        "dangerous_rule": DangerousRule,
        "dangerous_path": DangerousPath,
    }

    if module != "system":
        model = model_map[module]
    else:
        model = system_model_map[child_module]

    queryset = model.objects.filter(team__contains=int(group_id))

    # 计算总数
    total_count = queryset.count()

    # 计算分页
    start = (page - 1) * page_size
    end = page * page_size

    # 获取当前页的数据
    data_list = queryset.values("id", "name")[start:end]

    return {
        "count": total_count,
        "items": list(data_list),
    }


@nats_client.register
def ansible_task_callback(data: dict):
    """
    Ansible 任务执行回调

    由新版本 Ansible Executor 执行完成后调用，更新 JobExecution 状态和结果。

    仅支持结构化的 per-host 结果数组，不再兼容旧版字符串输出。

    Args:
        data: 回调数据，包含以下字段：
            - task_id: 任务ID（对应 JobExecution.id）
            - task_type: 任务类型（adhoc/playbook）
            - status: 执行状态（success/failed）
            - success: 任务级是否成功
            - result: per-host 结果数组，每项至少包含 host/status/stdout/stderr/exit_code/error_message
            - error: 错误信息
            - started_at: 开始时间（ISO格式）
            - finished_at: 结束时间（ISO格式）

    Returns:
        {"success": True/False, "message": "..."}
    """
    logger.info(f"[ansible_task_callback] {data}")

    task_id = data.get("task_id")
    if not task_id:
        logger.warning("[ansible_task_callback] 缺少 task_id")
        return {"success": False, "message": "缺少 task_id"}

    try:
        execution = JobExecution.objects.get(id=task_id)
    except JobExecution.DoesNotExist:
        logger.warning(f"[ansible_task_callback] 执行记录不存在: task_id={task_id}")
        return {"success": False, "message": f"执行记录不存在: {task_id}"}

    # 检查是否已经是终态（避免重复处理）
    if execution.status in ExecutionStatus.TERMINAL_STATES:
        logger.info(f"[ansible_task_callback] 任务已处于终态: task_id={task_id}, status={execution.status}")
        return {"success": True, "message": "任务已处理"}

    # 解析新版本结构化回调数据
    raw_result = data.get("result", [])
    error_output = data.get("error", "")
    finished_at_str = data.get("finished_at")
    target_list = execution.target_list or []
    execution_results = []

    if not (isinstance(raw_result, list) and raw_result and all(isinstance(item, dict) for item in raw_result)):
        logger.warning(f"[ansible_task_callback] 非法的新版本结果格式: task_id={task_id}, result={raw_result}")
        return {"success": False, "message": "非法的新版本结果格式"}

    target_map = {}
    for target_info in target_list:
        target_map[str(target_info.get("ip", ""))] = target_info
        target_map[str(target_info.get("target_id", ""))] = target_info

    seen_target_keys = set()
    for host_result in raw_result:
        host_key = str(host_result.get("host", ""))
        target_info = target_map.get(host_key)
        if not target_info:
            logger.warning(f"[ansible_task_callback] 结果中的主机未匹配到目标: task_id={task_id}, host={host_key}")
            return {"success": False, "message": f"结果中的主机未匹配到目标: {host_key}"}

        target_key = str(target_info.get("target_id", ""))
        if target_key in seen_target_keys:
            logger.warning(f"[ansible_task_callback] 结果中的主机重复: task_id={task_id}, host={host_key}")
            return {"success": False, "message": f"结果中的主机重复: {host_key}"}
        seen_target_keys.add(target_key)

        host_status = host_result.get("status")
        final_status = ExecutionStatus.SUCCESS if host_status == "success" else ExecutionStatus.FAILED
        execution_results.append(
            {
                "target_key": target_key,
                "name": target_info.get("name", host_key),
                "ip": target_info.get("ip", host_key),
                "status": final_status,
                "stdout": str(host_result.get("stdout", "")),
                "stderr": str(host_result.get("stderr", "")),
                "exit_code": host_result.get("exit_code", 0),
                "error_message": str(host_result.get("error_message", "")),
                "started_at": execution.started_at.isoformat() if execution.started_at else "",
                "finished_at": finished_at_str or timezone.now().isoformat(),
            }
        )

    if len(execution_results) < len(target_list):
        existing_keys = {item["target_key"] for item in execution_results}
        for target_info in target_list:
            target_key = str(target_info.get("target_id", ""))
            if target_key in existing_keys:
                continue
            execution_results.append(
                {
                    "target_key": target_key,
                    "name": target_info.get("name", ""),
                    "ip": target_info.get("ip", ""),
                    "status": ExecutionStatus.FAILED,
                    "stdout": "",
                    "stderr": str(error_output or "未收到该目标执行结果"),
                    "exit_code": 1,
                    "error_message": str(error_output or "未收到该目标执行结果"),
                    "started_at": execution.started_at.isoformat() if execution.started_at else "",
                    "finished_at": finished_at_str or timezone.now().isoformat(),
                }
            )

    # 更新执行记录
    execution.status = (
        ExecutionStatus.FAILED if any(item.get("status") == ExecutionStatus.FAILED for item in execution_results) else ExecutionStatus.SUCCESS
    )
    execution.execution_results = execution_results
    execution.finished_at = timezone.now()
    execution.success_count = sum(1 for item in execution_results if item.get("status") == ExecutionStatus.SUCCESS)
    execution.failed_count = sum(1 for item in execution_results if item.get("status") == ExecutionStatus.FAILED)
    execution.save(
        update_fields=[
            "status",
            "execution_results",
            "finished_at",
            "success_count",
            "failed_count",
            "updated_at",
        ]
    )

    logger.info(f"[ansible_task_callback] 任务完成: task_id={task_id}, status={execution.status}")

    # 清理 Playbook 执行中转到 NATS OS 的临时文件
    if execution.playbook_id:
        nats_file_key = f"job-playbooks/{task_id}/{execution.playbook.file_name}" if execution.playbook else None
        if nats_file_key:
            try:
                async_to_sync(delete_s3_file)(nats_file_key)
                logger.info(f"[ansible_task_callback] 已清理 NATS OS 中转文件: {nats_file_key}")
            except Exception as e:
                logger.warning(f"[ansible_task_callback] 清理 NATS OS 中转文件失败: {nats_file_key}, error={e}")

    return {"success": True, "message": "回调处理成功"}
