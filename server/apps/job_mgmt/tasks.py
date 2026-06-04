"""作业执行 Celery 任务入口"""

from datetime import timedelta

from asgiref.sync import async_to_sync
from celery import current_app, shared_task
from django.utils import timezone

from apps.core.logger import job_logger as logger
from apps.core.utils.safe_requests import safe_post
from apps.core.utils.ssrf_validator import SSRFError, SSRFValidator
from apps.job_mgmt.constants import ConcurrencyPolicy, ExecutionStatus, JobType, TriggerSource
from apps.job_mgmt.models import DistributionFile, JobExecution, ScheduledTask
from apps.job_mgmt.services import FileDistributionRunner, ScriptExecutionRunner, ScriptParamsService
from apps.job_mgmt.services.dangerous_checker import DangerousChecker
from apps.job_mgmt.services.playbook_execution import PlaybookExecution
from apps.job_mgmt.utils.callback_signer import get_signed_headers
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

    # 并发策略检查
    policy = scheduled_task.concurrency_policy
    logger.info(f"[execute_scheduled_task] 并发策略检查: scheduled_task_id={scheduled_task_id}, " f"name={scheduled_task.name}, policy={policy}")
    if policy in (ConcurrencyPolicy.SKIP, ConcurrencyPolicy.QUEUE):
        running_executions = JobExecution.objects.filter(
            scheduled_task_id=scheduled_task_id,
            status__in=[ExecutionStatus.PENDING, ExecutionStatus.RUNNING],
        )
        running_count = running_executions.count()
        if running_count > 0:
            running_ids = list(running_executions.values_list("id", flat=True)[:5])
            if policy == ConcurrencyPolicy.SKIP:
                logger.info(
                    f"[execute_scheduled_task] 并发策略=skip, 上次执行未完成, 跳过本次: "
                    f"scheduled_task_id={scheduled_task_id}, "
                    f"未完成执行数={running_count}, 未完成执行ID={running_ids}"
                )
                return
            elif policy == ConcurrencyPolicy.QUEUE:
                logger.info(
                    f"[execute_scheduled_task] 并发策略=queue, 上次执行未完成, 延迟30秒重试: "
                    f"scheduled_task_id={scheduled_task_id}, "
                    f"未完成执行数={running_count}, 未完成执行ID={running_ids}"
                )
                execute_scheduled_task.apply_async(
                    args=[scheduled_task_id],
                    countdown=30,
                )
                return
        else:
            logger.info(f"[execute_scheduled_task] 并发策略={policy}, 无未完成执行, 继续触发: " f"scheduled_task_id={scheduled_task_id}")
    else:
        logger.info(f"[execute_scheduled_task] 并发策略=run, 无条件触发: " f"scheduled_task_id={scheduled_task_id}")

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

    # 脚本内容和类型：优先从关联的 Script 对象获取，回退到定时任务上的临时输入字段
    script_content = scheduled_task.script_content or ""
    script_type = scheduled_task.script_type or ""
    if scheduled_task.script:
        script_content = scheduled_task.script.content or script_content
        script_type = scheduled_task.script.script_type or script_type

    # 高危命令/路径检测（定时任务也需要检查，脚本库内容可能已变更）
    team = scheduled_task.team or []
    if scheduled_task.job_type == JobType.SCRIPT and script_content:
        check_result = DangerousChecker.check_command(script_content, team)
        if not check_result.can_execute:
            forbidden_rules = [r["rule_name"] for r in check_result.forbidden]
            logger.warning(f"[execute_scheduled_task] 脚本包含高危命令，禁止执行: " f"scheduled_task_id={scheduled_task_id}, rules={forbidden_rules}")
            return
    if scheduled_task.job_type == JobType.FILE_DISTRIBUTION and scheduled_task.target_path:
        check_result = DangerousChecker.check_path(scheduled_task.target_path, team)
        if not check_result.can_execute:
            forbidden_rules = [r["rule_name"] for r in check_result.forbidden]
            logger.warning(
                f"[execute_scheduled_task] 目标路径为高危路径，禁止分发: "
                f"scheduled_task_id={scheduled_task_id}, path={scheduled_task.target_path}, rules={forbidden_rules}"
            )
            return

    execution = JobExecution.objects.create(
        name=scheduled_task.name,
        job_type=scheduled_task.job_type,
        trigger_source=TriggerSource.SCHEDULED,
        status=ExecutionStatus.PENDING,
        script=scheduled_task.script,
        playbook=scheduled_task.playbook,
        playbook_version=scheduled_task.playbook.version if scheduled_task.playbook else "",
        scheduled_task=scheduled_task,
        params=params_str,
        script_type=script_type,
        script_content=script_content,
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
    # 仅清理临时文件（is_permanent=False），永久文件不清理
    expired_files = DistributionFile.objects.filter(created_at__lt=threshold, is_permanent=False)
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
    result = None
    if job_type == JobType.SCRIPT:
        result = current_app.send_task("apps.job_mgmt.tasks.execute_script_task", args=[execution_id])
    elif job_type == JobType.FILE_DISTRIBUTION:
        result = current_app.send_task("apps.job_mgmt.tasks.distribute_files_task", args=[execution_id])
    elif job_type == JobType.PLAYBOOK:
        result = current_app.send_task("apps.job_mgmt.tasks.execute_playbook_task", args=[execution_id])
    else:
        return False

    # 保存 Celery task_id 到执行记录，用于取消时 revoke
    if result:
        JobExecution.objects.filter(id=execution_id).update(celery_task_id=result.id)
    return True


@shared_task(
    bind=True,
    max_retries=5,
    default_retry_delay=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
)
def do_callback_task(self, url: str, payload: dict, execution_id: int) -> None:
    """
    执行回调 POST 请求（Celery 持久化任务）。

    失败时由 Celery 自动重试（指数退避: ~5s → 10s → 20s → 40s → 80s，最多 5 次）。
    任务持久化到 broker，worker 重启后仍会继续执行。

    安全特性：
    - SSRF 防护：二次校验 URL，仅阻断云元数据地址（允许内网回调）
    - 签名认证：请求头包含 HMAC-SHA256 签名，供接收方验证来源
    """
    # 二次 SSRF 校验（宽松模式，仅阻断云元数据）
    try:
        SSRFValidator.validate_callback(url)
    except SSRFError as e:
        logger.error(f"[callback] SSRF 校验失败，拒绝回调: execution_id={execution_id}, url={url}, error={e}")
        # SSRF 校验失败不重试，直接返回
        return

    # 生成签名请求头
    headers = get_signed_headers(payload)

    try:
        resp = safe_post(url, json=payload, headers=headers, timeout=10)
        if 200 <= resp.status_code < 300:
            logger.info(f"[callback] 回调成功: execution_id={execution_id}, url={url}")
            return
        else:
            error_msg = f"回调返回非 2xx: status_code={resp.status_code}"
            logger.warning(
                f"[callback] {error_msg}: execution_id={execution_id}, " f"url={url}, attempt={self.request.retries + 1}/{self.max_retries + 1}"
            )
            raise RuntimeError(error_msg)
    except SSRFError as e:
        # safe_post 内部的 SSRF 校验失败（如重定向到内网）
        logger.error(f"[callback] 请求过程中 SSRF 校验失败: execution_id={execution_id}, url={url}, error={e}")
        return
    except RuntimeError:
        raise
    except Exception as e:
        logger.warning(
            f"[callback] 回调异常: execution_id={execution_id}, " f"url={url}, attempt={self.request.retries + 1}/{self.max_retries + 1}, error={e}"
        )
        raise
