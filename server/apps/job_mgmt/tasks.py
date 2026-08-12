"""作业执行 Celery 任务入口"""

from datetime import timedelta
from uuid import uuid4

from asgiref.sync import async_to_sync
from celery import current_app, shared_task
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.core.logger import job_logger as logger
from apps.core.utils.safe_requests import safe_post
from apps.core.utils.ssrf_validator import SSRFError, SSRFValidator
from apps.job_mgmt.config import (
    CALLBACK_CANCEL_RECONCILE_GRACE_SECONDS,
    DISTRIBUTION_FILE_CLEANUP_BATCH_SIZE,
    DISTRIBUTION_FILE_CLEANUP_MAX_CONCURRENCY,
    SCHEDULED_TASK_QUEUE_RETRY_COUNTDOWN,
)
from apps.job_mgmt.constants import ConcurrencyPolicy, ExecutionStatus, JobType, TriggerSource
from apps.job_mgmt.models import DistributionFile, JobExecution, ScheduledTask
from apps.job_mgmt.services import FileDistributionRunner, ScriptExecutionRunner, ScriptParamsService
from apps.job_mgmt.services.dangerous_checker import DangerousChecker
from apps.job_mgmt.services.playbook_execution import PlaybookExecution
from apps.job_mgmt.services.scheduled_task_authz import (
    ScheduledTaskTeamBoundaryError,
    disable_scheduled_task_and_schedule,
    validate_scheduled_task_resource_boundary,
)
from apps.job_mgmt.services.scheduled_task_service import ScheduledTaskService
from apps.job_mgmt.utils.callback_signer import get_signed_headers
from apps.node_mgmt.utils.s3 import delete_s3_files


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
def finalize_cancelling_execution(execution_id: int):
    """兜底收敛：CANCELLING 滞留超时后强制收敛为 CANCELLED 终态。

    与真实回调争用同一执行行锁；已有结果保留，对缺失目标补一条"远端结果未知"的
    CANCELLED 结果，并在同一事务持久化完成副作用。
    """
    from apps.job_mgmt.services.completion_outbox_service import enqueue_terminal_effects

    with transaction.atomic():
        execution = JobExecution.objects.select_for_update().filter(id=execution_id).first()
        if execution is None or execution.status != ExecutionStatus.CANCELLING:
            return

        results = list(execution.execution_results or [])
        have_keys = {str(result.get("target_key")) for result in results}
        for target in execution.target_list or []:
            target_key = str(target.get("node_id") or target.get("target_id", ""))
            if target_key in have_keys:
                continue
            results.append(
                {
                    "target_key": target_key,
                    "name": target.get("name", ""),
                    "ip": target.get("ip", ""),
                    "status": ExecutionStatus.CANCELLED,
                    "error_message": "任务已取消，远端结果未知",
                }
            )

        execution.status = ExecutionStatus.CANCELLED
        execution.terminal_source = JobExecution.TerminalSource.CANCEL_TIMEOUT
        execution.cancel_finalize_at = None
        execution.finished_at = timezone.now()
        execution.execution_results = results
        execution.success_count = sum(1 for result in results if result.get("status") == ExecutionStatus.SUCCESS)
        execution.failed_count = sum(1 for result in results if result.get("status") in (ExecutionStatus.FAILED, ExecutionStatus.TIMEOUT))
        execution.save(
            update_fields=[
                "status",
                "terminal_source",
                "cancel_finalize_at",
                "finished_at",
                "execution_results",
                "success_count",
                "failed_count",
                "updated_at",
            ]
        )
        enqueue_terminal_effects(
            execution,
            not_before=timezone.now() + timedelta(seconds=CALLBACK_CANCEL_RECONCILE_GRACE_SECONDS),
        )

    logger.info(f"[finalize_cancelling_execution] 取消中任务已强制收敛为 CANCELLED: execution_id={execution_id}")


@shared_task(max_retries=0)
def deliver_job_completion_outbox(record_id: int):
    """投递一条作业完成副作用；失败状态及退避时间由数据库 outbox 记录。"""
    from apps.job_mgmt.services.completion_outbox_service import deliver_outbox_record

    return deliver_outbox_record(record_id)


@shared_task(max_retries=0)
def dispatch_pending_job_completion_outbox():
    """重扫待投递副作用，并补偿 broker 入队失败的取消收敛。"""
    from apps.job_mgmt.services.completion_outbox_service import due_outbox_ids

    record_ids = due_outbox_ids()
    for record_id in record_ids:
        try:
            deliver_job_completion_outbox.delay(record_id)
        except Exception:
            logger.exception("job completion outbox reschedule failed: outbox_id=%s", record_id)

    due_execution_ids = list(
        JobExecution.objects.filter(
            status=ExecutionStatus.CANCELLING,
            cancel_finalize_at__isnull=False,
            cancel_finalize_at__lte=timezone.now(),
        )
        .order_by("cancel_finalize_at", "pk")
        .values_list("pk", flat=True)[:200]
    )
    for execution_id in due_execution_ids:
        try:
            finalize_cancelling_execution.delay(execution_id)
        except Exception:
            logger.exception("cancelling execution reschedule failed: execution_id=%s", execution_id)
    return {"scheduled": len(record_ids), "cancel_scheduled": len(due_execution_ids)}


@shared_task(max_retries=0)
def execute_scheduled_task(scheduled_task_id: int):
    logger.info(f"[execute_scheduled_task] 开始执行定时任务: scheduled_task_id={scheduled_task_id}")

    # ---- 阶段 1: 临界区(行锁 + 事务)----
    # 授权复核后一直持有任务与稳定资源行锁，直到创建 PENDING execution，
    # 防止并发更新让校验结论与执行快照不一致。
    queue_retry_needed = False
    execution_id = None
    job_type = None

    with transaction.atomic():
        try:
            scheduled_task = ScheduledTask.objects.select_for_update().get(id=scheduled_task_id)
        except ScheduledTask.DoesNotExist:
            logger.error(f"[execute_scheduled_task] 定时任务不存在: scheduled_task_id={scheduled_task_id}")
            return

        if not scheduled_task.is_enabled:
            if not disable_scheduled_task_and_schedule(scheduled_task_id):
                logger.error(
                    f"[execute_scheduled_task] 已禁用任务的 Beat 调度同步仍失败，将在下次触发重试: "
                    f"scheduled_task_id={scheduled_task_id}"
                )
            logger.info(f"[execute_scheduled_task] 定时任务已禁用: scheduled_task_id={scheduled_task_id}")
            return

        try:
            validate_scheduled_task_resource_boundary({}, instance=scheduled_task, lock_resources=True)
        except ScheduledTaskTeamBoundaryError as exc:
            disabled = disable_scheduled_task_and_schedule(scheduled_task_id)
            outcome = "任务与调度已禁用" if disabled else "调度同步失败，任务保持启用以便下次重试"
            logger.error(
                f"[execute_scheduled_task] 锁内团队资源边界复核失败，{outcome}: "
                f"scheduled_task_id={scheduled_task_id}, field={exc.field}, reason={exc.message}"
            )
            return

        team = scheduled_task.team or []
        script_content = scheduled_task.script_content or ""
        script_type = scheduled_task.script_type or ""
        if scheduled_task.script:
            script_content = scheduled_task.script.content or script_content
            script_type = scheduled_task.script.script_type or script_type

        job_type = scheduled_task.job_type
        if job_type == JobType.SCRIPT and script_content:
            check_result = DangerousChecker.check_command(script_content, team)
            if not check_result.can_execute:
                forbidden_rules = [r["rule_name"] for r in check_result.forbidden]
                logger.warning(
                    f"[execute_scheduled_task] 脚本包含高危命令，禁止执行: "
                    f"scheduled_task_id={scheduled_task_id}, rules={forbidden_rules}"
                )
                return
        if job_type == JobType.FILE_DISTRIBUTION and scheduled_task.target_path:
            check_result = DangerousChecker.check_path(scheduled_task.target_path, team)
            if not check_result.can_execute:
                forbidden_rules = [r["rule_name"] for r in check_result.forbidden]
                logger.warning(
                    f"[execute_scheduled_task] 目标路径为高危路径，禁止分发: "
                    f"scheduled_task_id={scheduled_task_id}, path={scheduled_task.target_path}, rules={forbidden_rules}"
                )
                return

        target_list = scheduled_task.target_list or []
        if not target_list:
            logger.warning(f"[execute_scheduled_task] 定时任务无执行目标: scheduled_task_id={scheduled_task_id}")
            return

        params = scheduled_task.params if isinstance(scheduled_task.params, list) else []
        resolved_params = ScriptParamsService.resolve_params(params, script=scheduled_task.script)
        params_str = ScriptParamsService.params_to_string(resolved_params)
        playbook_version = scheduled_task.playbook.version if scheduled_task.playbook else ""

        # 并发策略检查
        policy = scheduled_task.concurrency_policy
        logger.info(f"[execute_scheduled_task] 并发策略检查: scheduled_task_id={scheduled_task_id}, " f"name={scheduled_task.name}, policy={policy}")
        if policy in (ConcurrencyPolicy.SKIP, ConcurrencyPolicy.QUEUE):
            running_executions = JobExecution.objects.filter(
                scheduled_task_id=scheduled_task_id,
                trigger_source=TriggerSource.SCHEDULED,
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
                # QUEUE 命中:不在事务内调 broker,仅设标志,事务提交后由阶段 3 重投,避免 broker
                # 抖动拉长数据库锁等待
                queue_retry_needed = True
                logger.info(
                    f"[execute_scheduled_task] 并发策略=queue, 上次执行未完成, 延迟30秒重试: "
                    f"scheduled_task_id={scheduled_task_id}, "
                    f"未完成执行数={running_count}, 未完成执行ID={running_ids}"
                )
            else:
                logger.info(f"[execute_scheduled_task] 并发策略={policy}, 无未完成执行, 继续触发: " f"scheduled_task_id={scheduled_task_id}")
        else:
            logger.info(f"[execute_scheduled_task] 并发策略=run, 无条件触发: " f"scheduled_task_id={scheduled_task_id}")

        if not queue_retry_needed:
            now = timezone.now()
            # run_count 走 F() 表达式,updated_at 必须显式带(QuerySet.update 不触发 auto_now)
            ScheduledTask.objects.filter(id=scheduled_task_id).update(
                run_count=F("run_count") + 1,
                last_run_at=now,
                updated_at=now,
            )

            execution = JobExecution.objects.create(
                name=scheduled_task.name,
                job_type=job_type,
                trigger_source=TriggerSource.SCHEDULED,
                status=ExecutionStatus.PENDING,
                script=scheduled_task.script,
                playbook=scheduled_task.playbook,
                playbook_version=playbook_version,
                scheduled_task=scheduled_task,
                enforce_scheduled_team_boundary=True,
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
            execution_id = execution.id
            logger.info(f"[execute_scheduled_task] 创建执行记录: execution_id={execution.id}, targets={len(target_list)}")

    # ---- 阶段 2: 事务外副作用(QUEUE 重试 / broker 派发)----
    if queue_retry_needed:
        execute_scheduled_task.apply_async(
            args=[scheduled_task_id],
            countdown=SCHEDULED_TASK_QUEUE_RETRY_COUNTDOWN,
        )
        return
    if execution_id is None:
        return
    # broker 不可用 / 未知作业类型时置 FAILED 避免 PENDING 孤立
    if not _dispatch_execution_job(job_type, execution_id):
        logger.error(
            f"[execute_scheduled_task] 作业派发失败（broker 不可用或作业类型未知）: "
            f"scheduled_task_id={scheduled_task_id}, execution_id={execution_id}, job_type={job_type}"
        )
        execution = JobExecution.objects.get(id=execution_id)
        execution.status = ExecutionStatus.FAILED
        execution.save(update_fields=["status", "updated_at"])
        return

    logger.info(f"[execute_scheduled_task] 定时任务触发完成: scheduled_task_id={scheduled_task_id}, execution_id={execution_id}")


@shared_task(max_retries=0)
def cleanup_expired_distribution_files_task():
    # 清理所有已到期文件（expire_at <= 当前时间）
    expire_before = timezone.now()
    expired_files = DistributionFile.objects.filter(expire_at__lte=expire_before)
    total_count = expired_files.count()
    if total_count == 0:
        logger.info("[cleanup_expired_distribution_files_task] 没有过期文件需要清理")
        return
    logger.info(f"[cleanup_expired_distribution_files_task] 开始清理 {total_count} 个过期文件")
    success_count = 0
    fail_count = 0
    cursor = None
    while True:
        batch_query = expired_files
        if cursor is not None:
            created_at, file_id = cursor
            batch_query = batch_query.filter(Q(created_at__lt=created_at) | Q(created_at=created_at, id__lt=file_id))
        batch = list(
            batch_query.order_by("-created_at", "-id").values("id", "file_key", "original_name", "created_at")[:DISTRIBUTION_FILE_CLEANUP_BATCH_SIZE]
        )
        if not batch:
            break
        cursor = batch[-1]["created_at"], batch[-1]["id"]

        try:
            delete_results = async_to_sync(delete_s3_files)(
                [item["file_key"] for item in batch],
                max_concurrency=DISTRIBUTION_FILE_CLEANUP_MAX_CONCURRENCY,
            )
        except Exception as error:
            delete_results = {item["file_key"]: error for item in batch}

        successful_files = []
        for item in batch:
            error = delete_results.get(item["file_key"], RuntimeError("对象存储未返回删除结果"))
            if error is None:
                successful_files.append(item)
            else:
                fail_count += 1
                logger.warning(f"[cleanup_expired_distribution_files_task] 删除失败: {item['file_key']}, error={error}")

        if successful_files:
            try:
                DistributionFile.objects.filter(id__in=[item["id"] for item in successful_files]).delete()
            except Exception as error:
                fail_count += len(successful_files)
                for item in successful_files:
                    logger.warning(f"[cleanup_expired_distribution_files_task] 删除失败: {item['file_key']}, error={error}")
            else:
                success_count += len(successful_files)
                for item in successful_files:
                    logger.info(f"[cleanup_expired_distribution_files_task] 已删除: {item['original_name']} ({item['file_key']})")
    logger.info(f"[cleanup_expired_distribution_files_task] 清理完成: success={success_count}, fail={fail_count}")


_JOB_TYPE_TO_TASK_NAME = {
    JobType.SCRIPT: "apps.job_mgmt.tasks.execute_script_task",
    JobType.FILE_DISTRIBUTION: "apps.job_mgmt.tasks.distribute_files_task",
    JobType.PLAYBOOK: "apps.job_mgmt.tasks.execute_playbook_task",
}


def _dispatch_execution_job(job_type: str, execution_id: int) -> bool:
    """持久化 Celery task id 后派发执行任务。

    Returns ``False`` 当作业类型未知、执行记录不可写或 broker 派发失败；调用方应据此把
    执行记录置为 FAILED，避免留下 PENDING 孤立记录。
    """
    task_name = _JOB_TYPE_TO_TASK_NAME.get(job_type)
    if not task_name:
        return False

    celery_task_id = uuid4().hex
    try:
        updated = JobExecution.objects.filter(id=execution_id).update(celery_task_id=celery_task_id)
    except Exception as e:
        logger.exception(f"[_dispatch_execution_job] Celery 任务ID持久化失败: " f"execution_id={execution_id}, job_type={job_type}, error={e}")
        return False
    if not updated:
        logger.error(f"[_dispatch_execution_job] 执行记录不存在: execution_id={execution_id}, job_type={job_type}")
        return False

    try:
        current_app.send_task(task_name, args=[execution_id], task_id=celery_task_id)
    except Exception as e:
        logger.exception(f"[_dispatch_execution_job] Celery 派发失败: execution_id={execution_id}, job_type={job_type}, error={e}")
        try:
            # 发布异常不代表 broker 一定未接收。保留已持久化的 ID，并尽力撤销可能已入队的任务。
            current_app.control.revoke(celery_task_id)
        except Exception as revoke_error:
            logger.exception(
                f"[_dispatch_execution_job] Celery 任务撤销失败: " f"execution_id={execution_id}, task_id={celery_task_id}, error={revoke_error}"
            )
        return False

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


@shared_task(max_retries=0)
def do_nats_callback_task(subject: str, payload: dict, execution_id: int) -> None:
    """旧的非终态 nats 回调通道：用 request/reply 把作业结果投递到指定主题。

    在 Celery worker（同步上下文）中执行；消费方未注册或处理失败时仅记录，不影响
    作业状态。Ansible 回调与取消兜底终态不走此 best-effort 入口，而由 completion
    outbox 持久化重试。
    """
    try:
        from apps.job_mgmt.services.callback_service import publish_job_result_to_subject

        publish_job_result_to_subject(subject, payload)
        logger.info(f"[callback][nats] 回调成功: execution_id={execution_id}, subject={subject}, status={payload.get('status')}")
    except Exception as e:
        logger.warning(f"[callback][nats] 回调失败: execution_id={execution_id}, subject={subject}, error={e}")
