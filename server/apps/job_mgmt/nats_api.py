"""Job Management NATS API - 用于数据权限规则"""

from django.utils import timezone

import nats_client
from apps.core.logger import job_logger as logger
from apps.job_mgmt.constants import ExecutionStatus
from apps.job_mgmt.models import DangerousPath, DangerousRule, JobExecution, Playbook, ScheduledTask, Script, Target


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

    由 Ansible Executor 执行完成后调用，更新 JobExecution 状态和结果。

    Args:
        data: 回调数据，包含以下字段：
            - task_id: 任务ID（对应 JobExecution.id）
            - task_type: 任务类型（adhoc/playbook）
            - status: 执行状态（success/failed）
            - success: 是否成功
            - result: ansible 命令输出
            - error: 错误信息
            - started_at: 开始时间（ISO格式）
            - finished_at: 结束时间（ISO格式）

    Returns:
        {"success": True/False, "message": "..."}
    """
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

    # 解析回调数据
    success = data.get("success", False)
    result_output = data.get("result", "")
    error_output = data.get("error", "")
    finished_at_str = data.get("finished_at")

    # 确定最终状态
    final_status = ExecutionStatus.SUCCESS if success else ExecutionStatus.FAILED

    # 构建执行结果
    target_list = execution.target_list or []
    execution_results = []
    for target_info in target_list:
        target_result = {
            "target_key": str(target_info.get("target_id", "")),
            "name": target_info.get("name", ""),
            "ip": target_info.get("ip", ""),
            "status": final_status,
            "stdout": result_output,
            "stderr": error_output,
            "exit_code": 0 if success else 1,
            "error_message": error_output if not success else "",
            "started_at": execution.started_at.isoformat() if execution.started_at else "",
            "finished_at": finished_at_str or timezone.now().isoformat(),
        }
        execution_results.append(target_result)

    # 更新执行记录
    execution.status = final_status
    execution.execution_results = execution_results
    execution.finished_at = timezone.now()
    execution.success_count = len(target_list) if success else 0
    execution.failed_count = 0 if success else len(target_list)
    execution.save(update_fields=["status", "execution_results", "finished_at", "success_count", "failed_count", "updated_at"])

    logger.info(f"[ansible_task_callback] 任务完成: task_id={task_id}, status={final_status}")
    return {"success": True, "message": "回调处理成功"}
