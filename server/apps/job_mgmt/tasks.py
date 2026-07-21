"""作业执行 Celery 任务入口"""

from uuid import uuid4

from asgiref.sync import async_to_sync
from celery import current_app, shared_task
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.core.logger import job_logger as logger
from apps.core.utils.safe_requests import safe_post
from apps.core.utils.ssrf_validator import SSRFError, SSRFValidator
from apps.job_mgmt.config import SCHEDULED_TASK_QUEUE_RETRY_COUNTDOWN
from apps.job_mgmt.constants import ConcurrencyPolicy, ExecutionStatus, JobType, TriggerSource
from apps.job_mgmt.models import DistributionFile, JobExecution, ScheduledTask
from apps.job_mgmt.services import FileDistributionRunner, ScriptExecutionRunner, ScriptParamsService
from apps.job_mgmt.services.callback_service import send_callback
from apps.job_mgmt.services.dangerous_checker import DangerousChecker
from apps.job_mgmt.services.execution_stream_service import publish_done_sentinel
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
def finalize_cancelling_execution(execution_id: int):
    """兜底收敛：CANCELLING 滞留超时后强制收敛为 CANCELLED 终态。

    CAS 仅在仍为 CANCELLING 时生效（真实结果已回写并收敛后即为 no-op）；已有结果保留，
    对缺失结果的目标补一条"远端结果未知"的 CANCELLED 结果并发 done 哨兵关闭前端面板。
    """
    updated = JobExecution.objects.filter(id=execution_id, status=ExecutionStatus.CANCELLING).update(
        status=ExecutionStatus.CANCELLED, finished_at=timezone.now()
    )
    if not updated:
        return
    execution = JobExecution.objects.filter(id=execution_id).first()
    if execution is None:
        # CAS 命中后记录被删除（防御分支）：静默返回
        return

    results = list(execution.execution_results or [])
    have_keys = {str(r.get("target_key")) for r in results}
    for t in execution.target_list or []:
        tk = t.get("node_id") or str(t.get("target_id", ""))
        if tk in have_keys:
            continue
        results.append(
            {
                "target_key": tk,
                "name": t.get("name", ""),
                "ip": t.get("ip", ""),
                "status": ExecutionStatus.CANCELLED,
                "error_message": "任务已取消，远端结果未知",
            }
        )
        publish_done_sentinel(execution_id, tk, ExecutionStatus.CANCELLED)

    execution.execution_results = results
    execution.success_count = sum(1 for r in results if r.get("status") == ExecutionStatus.SUCCESS)
    execution.failed_count = sum(1 for r in results if r.get("status") in (ExecutionStatus.FAILED, ExecutionStatus.TIMEOUT))
    execution.save(update_fields=["execution_results", "success_count", "failed_count", "updated_at"])
    logger.info(f"[finalize_cancelling_execution] 取消中任务已强制收敛为 CANCELLED: execution_id={execution_id}")
    # 超时兜底取消也是终态，补发完成通知（HTTP 回调 + 告警推送）
    send_callback(execution)


@shared_task(max_retries=0)
def execute_scheduled_task(scheduled_task_id: int):
    logger.info(f"[execute_scheduled_task] 开始执行定时任务: scheduled_task_id={scheduled_task_id}")

    # ---- 阶段 1: 锁前预读 + 快速失败 ----
    # 仅做无锁的纯查询/纯计算,缩短后续临界区持有时间;危险检查、参数解析、目标列表
    # 解析与"并发策略检查 + run_count 自增 + 创建 PENDING execution"无竞争关系,放锁内只会
    # 拉长锁等待并放大 broker / cache 抖动对数据库锁的影响。
    try:
        st_snapshot = ScheduledTask.objects.select_related("script", "playbook").get(id=scheduled_task_id)
    except ScheduledTask.DoesNotExist:
        logger.error(f"[execute_scheduled_task] 定时任务不存在: scheduled_task_id={scheduled_task_id}")
        return
    if not st_snapshot.is_enabled:
        logger.info(f"[execute_scheduled_task] 定时任务已禁用: scheduled_task_id={scheduled_task_id}")
        return

    team = st_snapshot.team or []

    # 脚本内容和类型：优先从关联的 Script 对象获取，回退到定时任务上的临时输入字段。
    # 危险命令预检必须使用解析后的脚本内容，不能漏掉脚本库模式。
    script_content = st_snapshot.script_content or ""
    script_type = st_snapshot.script_type or ""
    if st_snapshot.script:
        script_content = st_snapshot.script.content or script_content
        script_type = st_snapshot.script.script_type or script_type

    if st_snapshot.job_type == JobType.SCRIPT and script_content:
        check_result = DangerousChecker.check_command(script_content, team)
        if not check_result.can_execute:
            forbidden_rules = [r["rule_name"] for r in check_result.forbidden]
            logger.warning(f"[execute_scheduled_task] 脚本包含高危命令，禁止执行: " f"scheduled_task_id={scheduled_task_id}, rules={forbidden_rules}")
            return
    if st_snapshot.job_type == JobType.FILE_DISTRIBUTION and st_snapshot.target_path:
        check_result = DangerousChecker.check_path(st_snapshot.target_path, team)
        if not check_result.can_execute:
            forbidden_rules = [r["rule_name"] for r in check_result.forbidden]
            logger.warning(
                f"[execute_scheduled_task] 目标路径为高危路径，禁止分发: "
                f"scheduled_task_id={scheduled_task_id}, path={st_snapshot.target_path}, rules={forbidden_rules}"
            )
            return

    target_list = st_snapshot.target_list or []
    if not target_list:
        logger.warning(f"[execute_scheduled_task] 定时任务无执行目标: scheduled_task_id={scheduled_task_id}")
        return

    # 处理参数：解析 is_modified=False 的参数并转换为字符串
    params = st_snapshot.params if isinstance(st_snapshot.params, list) else []
    resolved_params = ScriptParamsService.resolve_params(params, script=st_snapshot.script)
    params_str = ScriptParamsService.params_to_string(resolved_params)

    # ---- 阶段 2: 临界区(行锁 + 事务)----
    # 只保留"竞争状态相关的 SQL":并发策略检查 + run_count 自增 + 创建 PENDING execution。
    # run_count 用 F() 表达式走单条 SQL UPDATE,避免 read-modify-write 丢计数;
    # updated_at 用 QuerySet.update() 时不会触发 auto_now,必须显式带上,否则列表排序/审计失真。
    queue_retry_needed = False
    execution_id = None
    job_type = st_snapshot.job_type
    playbook_version = st_snapshot.playbook.version if st_snapshot.playbook else ""

    with transaction.atomic():
        scheduled_task = ScheduledTask.objects.select_for_update().get(id=scheduled_task_id)
        # 二次确认 is_enabled:锁前检查后到拿到锁之间可能被关闭
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
                name=st_snapshot.name,
                job_type=job_type,
                trigger_source=TriggerSource.SCHEDULED,
                status=ExecutionStatus.PENDING,
                script=st_snapshot.script,
                playbook=st_snapshot.playbook,
                playbook_version=playbook_version,
                scheduled_task=scheduled_task,
                params=params_str,
                script_type=script_type,
                script_content=script_content,
                files=st_snapshot.files,
                target_path=st_snapshot.target_path,
                timeout=st_snapshot.timeout,
                total_count=len(target_list),
                target_source=st_snapshot.target_source,
                target_list=target_list,
                team=st_snapshot.team,
                created_by=st_snapshot.created_by,
                updated_by=st_snapshot.updated_by,
            )
            execution_id = execution.id
            logger.info(f"[execute_scheduled_task] 创建执行记录: execution_id={execution.id}, targets={len(target_list)}")

    # ---- 阶段 3: 事务外副作用(QUEUE 重试 / broker 派发)----
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
    expired_files = DistributionFile.objects.filter(expire_at__lte=timezone.now())
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
        logger.exception(
            f"[_dispatch_execution_job] Celery 任务ID持久化失败: "
            f"execution_id={execution_id}, job_type={job_type}, error={e}"
        )
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
                f"[_dispatch_execution_job] Celery 任务撤销失败: "
                f"execution_id={execution_id}, task_id={celery_task_id}, error={revoke_error}"
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
    """nats 回调通道：把作业结果 publish 到指定 NATS 主题（fire-and-forget）。

    在 Celery worker（同步上下文）中执行 publish；消费方未注册接收函数时消息被 NATS 安全丢弃。
    任何异常仅记录不抛出，避免影响 web 通道回调及作业本身。
    """
    try:
        from apps.job_mgmt.services.callback_service import publish_job_result_to_subject

        publish_job_result_to_subject(subject, payload)
        logger.info(f"[callback][nats] 回调成功: execution_id={execution_id}, subject={subject}, status={payload.get('status')}")
    except Exception as e:
        logger.warning(f"[callback][nats] 回调失败: execution_id={execution_id}, subject={subject}, error={e}")
