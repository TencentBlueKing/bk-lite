"""作业执行 Celery 任务入口"""

from datetime import timedelta

from asgiref.sync import async_to_sync
from celery import current_app, shared_task
from django.utils import timezone

from apps.core.logger import job_logger as logger
from apps.job_mgmt.constants import ExecutionStatus, JobType
from apps.job_mgmt.models import DistributionFile, JobExecution, ScheduledTask
from apps.job_mgmt.services import FileDistributionRunner, ScriptExecutionRunner, ScriptParamsService
from apps.job_mgmt.services.playbook_execution import PlaybookExecution
from apps.node_mgmt.utils.s3 import delete_s3_file


@shared_task(max_retries=0)
def execute_script_task(execution_id: int):
    ScriptExecutionRunner(execution_id).run()


@shared_task(max_retries=0)
def distribute_files_task(execution_id: int):
    FileDistributionRunner(execution_id).run()


@shared_task(max_retries=0)
def execute_playbook_task(execution_id: int):
    client = PlaybookExecution(execution_id)
    client.run()


@shared_task(max_retries=0)
def execute_scheduled_task(scheduled_task_id: int):
    logger.info(f"[execute_scheduled_task] 开始执行定时任务: scheduled_task_id={scheduled_task_id}")
    try:
        scheduled_task = ScheduledTask.objects.get(id=scheduled_task_id)
    except ScheduledTask.DoesNotExist:
        logger.error(f"[execute_scheduled_task] 定时任务不存在: scheduled_task_id={scheduled_task_id}")
        return
    # 检查任务是否启用
    if not scheduled_task.is_enabled:
        logger.info(f"[execute_scheduled_task] 定时任务已禁用: scheduled_task_id={scheduled_task_id}")
        return
    # 更新上次执行时间和执行次数
    scheduled_task.last_run_at = timezone.now()
    scheduled_task.run_count += 1
    scheduled_task.save(update_fields=["last_run_at", "run_count", "updated_at"])
    # 获取执行目标列表
    target_list = scheduled_task.target_list or []
    if not target_list:
        logger.warning(f"[execute_scheduled_task] 定时任务无执行目标: scheduled_task_id={scheduled_task_id}")
        return
    # 处理参数：解析 is_modified=False 的参数并转换为字符串
    params = scheduled_task.params if isinstance(scheduled_task.params, list) else []
    resolved_params = ScriptParamsService.resolve_params(params, script=scheduled_task.script)
    params_str = ScriptParamsService.params_to_string(resolved_params)

    execution = JobExecution.objects.create(
        name=scheduled_task.name,
        job_type=scheduled_task.job_type,
        status=ExecutionStatus.PENDING,
        script=scheduled_task.script,
        playbook=scheduled_task.playbook,
        params=params_str,
        script_type=scheduled_task.script_type,
        script_content=scheduled_task.script_content,
        files=scheduled_task.files,
        target_path=scheduled_task.target_path,
        timeout=scheduled_task.timeout,
        total_count=len(target_list),
        target_source=scheduled_task.target_source,
        target_list=target_list,
        team=scheduled_task.team,
        created_by=scheduled_task.created_by,
        updated_by=scheduled_task.updated_by,
    )

    logger.info(f"[execute_scheduled_task] 创建执行记录: execution_id={execution.id}, targets={len(target_list)}")

    # 根据作业类型调用对应的执行任务
    if not _dispatch_execution_job(scheduled_task.job_type, execution.id):
        logger.error(f"[execute_scheduled_task] 未知的作业类型: {scheduled_task.job_type}")
        execution.status = ExecutionStatus.FAILED
        execution.save(update_fields=["status", "updated_at"])
        return

    logger.info(f"[execute_scheduled_task] 定时任务触发完成: scheduled_task_id={scheduled_task_id}, execution_id={execution.id}")


@shared_task(max_retries=0)
def cleanup_expired_distribution_files_task():
    threshold = timezone.now() - timedelta(days=7)
    expired_files = DistributionFile.objects.filter(created_at__lt=threshold)
    total_count = expired_files.count()
    if total_count == 0:
        logger.info("[cleanup_expired_distribution_files_task] 没有过期文件需要清理")
        return
    logger.info(f"[cleanup_expired_distribution_files_task] 开始清理 {total_count} 个过期文件")
    success_count = 0
    fail_count = 0
    for df in expired_files:
        try:
            # 删除 S3 文件
            async_to_sync(delete_s3_file)(df.file_key)
            # 删除数据库记录
            df.delete()
            success_count += 1
            logger.info(f"[cleanup_expired_distribution_files_task] 已删除: {df.original_name} ({df.file_key})")
        except Exception as e:
            fail_count += 1
            logger.warning(f"[cleanup_expired_distribution_files_task] 删除失败: {df.file_key}, error={e}")
    logger.info(f"[cleanup_expired_distribution_files_task] 清理完成: success={success_count}, fail={fail_count}")


def _dispatch_execution_job(job_type: str, execution_id: int) -> bool:
    if job_type == JobType.SCRIPT:
        current_app.send_task("apps.job_mgmt.tasks.execute_script_task", args=[execution_id])
        return True
    if job_type == JobType.FILE_DISTRIBUTION:
        current_app.send_task("apps.job_mgmt.tasks.distribute_files_task", args=[execution_id])
        return True
    if job_type == JobType.PLAYBOOK:
        current_app.send_task("apps.job_mgmt.tasks.execute_playbook_task", args=[execution_id])
        return True
    return False
