"""作业执行 Celery 任务

执行逻辑根据 Target 的 source 和 driver 字段选择不同的执行方式：
- source=sync: 使用 execute_local / download_to_local（通过 node_id 定位 Sidecar）
- source=manual: 使用 execute_ssh / download_to_remote（通过 SSH 凭据连接）
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional, Tuple

from celery import shared_task
from django.utils import timezone

from apps.core.logger import job_logger as logger
from apps.job_mgmt.constants import ExecutionStatus, ScriptType, TargetSource
from apps.job_mgmt.models import JobExecution, JobExecutionTarget
from apps.job_mgmt.services.dangerous_checker import DangerousChecker
from apps.job_mgmt.services.script_params_service import ScriptParamsService
from apps.rpc.executor import Executor

# 最大并发执行数
MAX_WORKERS = 10


def _get_ssh_private_key(target) -> Optional[str]:
    """从 Target 获取 SSH 私钥内容"""
    if not target.ssh_key_file:
        return None
    try:
        target.ssh_key_file.open("r")
        content = target.ssh_key_file.read()
        target.ssh_key_file.close()
        if isinstance(content, bytes):
            return content.decode("utf-8")
        return content
    except Exception:
        return None


def _format_error_message(e: Exception) -> str:
    """格式化异常信息，提取关键内容"""
    error_str = str(e)
    error_type = type(e).__name__

    # 提取常见关键字
    keywords = ["timeout", "connection", "refused", "denied", "permission", "authentication", "unreachable", "reset"]
    hints = [kw for kw in keywords if kw.lower() in error_str.lower()]

    if hints:
        return f"执行过程出错: {error_type} ({', '.join(hints)})"
    return f"执行过程出错: {error_type} - {error_str[:200]}" if len(error_str) > 200 else f"执行过程出错: {error_type} - {error_str}"


def _update_execution_status(execution: JobExecution, status: str, started_at: Optional[datetime] = None, finished_at: Optional[datetime] = None):
    """更新执行记录状态"""
    update_fields = ["status", "updated_at"]
    execution.status = status

    if started_at:
        execution.started_at = started_at
        update_fields.append("started_at")

    if finished_at:
        execution.finished_at = finished_at
        update_fields.append("finished_at")

    execution.save(update_fields=update_fields)


def _update_execution_counts(execution: JobExecution):
    """更新执行统计"""
    targets = execution.execution_targets.all()
    execution.success_count = targets.filter(status=ExecutionStatus.SUCCESS).count()
    execution.failed_count = targets.filter(status__in=[ExecutionStatus.FAILED, ExecutionStatus.TIMEOUT]).count()
    execution.save(update_fields=["success_count", "failed_count", "updated_at"])


def _update_target_status(
    target_detail: JobExecutionTarget,
    status: str,
    stdout: str = "",
    stderr: str = "",
    exit_code: Optional[int] = None,
    error_message: str = "",
    started_at: Optional[datetime] = None,
    finished_at: Optional[datetime] = None,
):
    """更新目标执行状态"""
    target_detail.status = status
    target_detail.stdout = stdout
    target_detail.stderr = stderr
    target_detail.exit_code = exit_code
    target_detail.error_message = error_message

    if started_at:
        target_detail.started_at = started_at
    if finished_at:
        target_detail.finished_at = finished_at

    target_detail.save()


def _get_shell_type(script_type: str) -> str:
    """获取 shell 类型映射"""
    return ScriptType.SHELL_MAPPING.get(script_type, "sh")


def _prepare_execution(execution_id: int, task_name: str) -> Tuple[Optional[JobExecution], list]:
    """
    任务执行前置处理

    Returns:
        (execution, target_details): 成功时返回执行记录和目标列表
        (None, []): 失败时返回
    """
    try:
        execution = JobExecution.objects.get(id=execution_id)
    except JobExecution.DoesNotExist:
        logger.error(f"[{task_name}] 执行记录不存在: execution_id={execution_id}")
        return None, []

    # 检查是否已取消
    if execution.status == ExecutionStatus.CANCELLED:
        logger.info(f"[{task_name}] 任务已取消: execution_id={execution_id}")
        return None, []

    # 更新状态为执行中
    started_at = timezone.now()
    _update_execution_status(execution, ExecutionStatus.RUNNING, started_at=started_at)

    # 获取所有待执行目标
    target_details = list(execution.execution_targets.filter(status=ExecutionStatus.PENDING))

    if not target_details:
        logger.warning(f"[{task_name}] 无待执行目标: execution_id={execution_id}")
        _update_execution_status(execution, ExecutionStatus.SUCCESS, finished_at=timezone.now())
        return None, []

    return execution, target_details


def _finalize_execution(execution: JobExecution, task_name: str):
    """任务执行后置处理：刷新状态、统计、确定最终结果"""
    # 刷新执行记录
    execution.refresh_from_db()

    # 检查是否被取消
    if execution.status == ExecutionStatus.CANCELLED:
        logger.info(f"[{task_name}] 任务被取消: execution_id={execution.id}")
        return

    # 更新统计和状态
    _update_execution_counts(execution)

    # 确定最终状态
    final_status = ExecutionStatus.FAILED if execution.failed_count > 0 else ExecutionStatus.SUCCESS
    _update_execution_status(execution, final_status, finished_at=timezone.now())

    logger.info(f"[{task_name}] 任务完成: execution_id={execution.id}, status={final_status}")


def _execute_script_on_target(target_detail: JobExecutionTarget, script_content: str, script_type: str, timeout: int) -> dict:
    """在单个目标上执行脚本"""
    target = target_detail.target
    result = {
        "target_id": target.id,
        "success": False,
        "stdout": "",
        "stderr": "",
        "exit_code": None,
        "error_message": "",
    }

    started_at = timezone.now()
    _update_target_status(target_detail, ExecutionStatus.RUNNING, started_at=started_at)

    try:
        shell = _get_shell_type(script_type)

        if target.source == TargetSource.SYNC:
            # 同步来源：使用 execute_local，node_id 是 Sidecar 实例 ID
            executor = Executor(target.node_id)
            exec_result = executor.execute_local(script_content, timeout=timeout, shell=shell)
        else:
            # 手动来源：使用 execute_ssh
            executor = Executor(target.node_id)  # 云区域 ID
            exec_result = executor.execute_ssh(
                command=script_content,
                host=target.ip,
                username=target.ssh_user,
                password=target.ssh_password if target.ssh_password else None,
                private_key=_get_ssh_private_key(target),
                timeout=timeout,
                port=target.ssh_port,
            )

        # 解析执行结果
        result["stdout"] = exec_result.get("stdout", "")
        result["stderr"] = exec_result.get("stderr", "")
        result["exit_code"] = exec_result.get("exit_code", exec_result.get("code", -1))
        result["success"] = result["exit_code"] == 0

    except Exception as e:
        result["error_message"] = _format_error_message(e)
        result["stderr"] = result["error_message"]
        logger.exception(f"目标 {target.name}({target.ip}) 脚本执行失败")

    finished_at = timezone.now()
    status = ExecutionStatus.SUCCESS if result["success"] else ExecutionStatus.FAILED
    _update_target_status(
        target_detail,
        status,
        stdout=result["stdout"],
        stderr=result["stderr"],
        exit_code=result["exit_code"],
        error_message=result["error_message"],
        finished_at=finished_at,
    )

    return result


@shared_task(bind=True, max_retries=0)
def execute_script_task(self, execution_id: int):
    """
    脚本执行任务

    Args:
        execution_id: 作业执行记录ID
    """
    task_name = "execute_script_task"
    logger.info(f"[{task_name}] 开始执行脚本任务: execution_id={execution_id}")

    execution, target_details = _prepare_execution(execution_id, task_name)
    if not execution:
        return

    # 高危命令检测（周期任务期间可能新增规则）
    check_result = DangerousChecker.check_command(execution.script_content, execution.team)
    if not check_result.can_execute:
        forbidden_rules = [r["rule_name"] for r in check_result.forbidden]
        error_msg = f"检测到高危命令，禁止执行: {', '.join(forbidden_rules)}"
        logger.warning(f"[{task_name}] {error_msg}")
        _update_execution_status(execution, ExecutionStatus.FAILED, finished_at=timezone.now())
        execution.execution_targets.update(status=ExecutionStatus.FAILED, error_message=error_msg)
        return

    # 获取脚本内容
    script_content = execution.script_content
    script_type = execution.script_type

    # 如果有命令行参数，附加到脚本内容末尾
    if execution.params:
        script_content = f"{script_content} {execution.params}"

    # 并发执行
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(target_details))) as pool:
        futures = {pool.submit(_execute_script_on_target, td, script_content, script_type, execution.timeout): td for td in target_details}
        for future in as_completed(futures):
            target_detail = futures[future]
            try:
                result = future.result()
                logger.info(f"[{task_name}] 目标 {target_detail.target.name} 执行完成: success={result['success']}")
            except Exception as e:
                logger.exception(f"[{task_name}] 目标 {target_detail.target.name} 执行异常: {e}")

    _finalize_execution(execution, task_name)


def _distribute_file_to_target(target_detail: JobExecutionTarget, files: list, target_path: str, timeout: int, overwrite: bool = True) -> dict:
    """分发文件到单个目标"""
    target = target_detail.target
    result = {
        "target_id": target.id,
        "success": True,
        "error_message": "",
        "file_results": [],
    }

    started_at = timezone.now()
    _update_target_status(target_detail, ExecutionStatus.RUNNING, started_at=started_at)

    try:
        for file_item in files:
            file_result = {
                "file_name": file_item.get("name", ""),
                "success": False,
                "error": "",
            }

            try:
                if target.source == TargetSource.SYNC:
                    # 同步来源：使用 download_to_local
                    executor = Executor(target.node_id)
                    exec_result = executor.download_to_local(
                        bucket_name=file_item.get("bucket_name", "job-mgmt-files"),
                        file_key=file_item.get("file_key", ""),
                        file_name=file_item.get("name", ""),
                        target_path=target_path,
                        timeout=timeout,
                        overwrite=overwrite,
                    )
                else:
                    # 手动来源：使用 download_to_remote
                    executor = Executor(target.node_id)
                    exec_result = executor.download_to_remote(
                        bucket_name=file_item.get("bucket_name", "job-mgmt-files"),
                        file_key=file_item.get("file_key", ""),
                        file_name=file_item.get("name", ""),
                        target_path=target_path,
                        host=target.ip,
                        username=target.ssh_user,
                        password=target.ssh_password if target.ssh_password else None,
                        private_key=_get_ssh_private_key(target),
                        timeout=timeout,
                        port=target.ssh_port,
                        overwrite=overwrite,
                    )

                # 检查结果
                if exec_result.get("code", -1) == 0 or exec_result.get("success", False):
                    file_result["success"] = True
                else:
                    file_result["error"] = exec_result.get("message", exec_result.get("stderr", "未知错误"))
                    result["success"] = False

            except Exception as e:
                file_result["error"] = str(e)
                result["success"] = False
                logger.exception(f"文件 {file_item.get('name')} 分发到 {target.name} 失败")

            result["file_results"].append(file_result)

    except Exception as e:
        result["success"] = False
        result["error_message"] = f"分发异常: {str(e)}"
        logger.exception(f"目标 {target.name}({target.ip}) 文件分发失败")

    finished_at = timezone.now()
    status = ExecutionStatus.SUCCESS if result["success"] else ExecutionStatus.FAILED

    # 汇总错误信息
    errors = [f"{fr['file_name']}: {fr['error']}" for fr in result["file_results"] if not fr["success"]]
    error_message = "\n".join(errors) if errors else result.get("error_message", "")

    _update_target_status(
        target_detail,
        status,
        stdout=f"分发 {len(files)} 个文件到 {target_path}",
        stderr=error_message,
        exit_code=0 if result["success"] else 1,
        error_message=error_message,
        finished_at=finished_at,
    )

    return result


@shared_task(bind=True, max_retries=0)
def distribute_files_task(self, execution_id: int):
    """
    文件分发任务

    Args:
        execution_id: 作业执行记录ID
    """
    task_name = "distribute_files_task"
    logger.info(f"[{task_name}] 开始执行文件分发任务: execution_id={execution_id}")

    execution, target_details = _prepare_execution(execution_id, task_name)
    if not execution:
        return

    # 高危路径检测（周期任务期间可能新增规则）
    check_result = DangerousChecker.check_path(execution.target_path, execution.team)
    if not check_result.can_execute:
        forbidden_rules = [r["rule_name"] for r in check_result.forbidden]
        error_msg = f"目标路径为高危路径，禁止分发: {', '.join(forbidden_rules)}"
        logger.warning(f"[{task_name}] {error_msg}")
        _update_execution_status(execution, ExecutionStatus.FAILED, finished_at=timezone.now())
        execution.execution_targets.update(status=ExecutionStatus.FAILED, error_message=error_msg)
        return

    # 获取文件列表、目标路径和覆盖策略
    files = execution.files
    target_path = execution.target_path
    overwrite = execution.overwrite_strategy == "overwrite"

    if not files:
        logger.warning(f"[{task_name}] 无文件需要分发: execution_id={execution_id}")
        _update_execution_status(execution, ExecutionStatus.SUCCESS, finished_at=timezone.now())
        return

    # 并发执行
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(target_details))) as pool:
        futures = {pool.submit(_distribute_file_to_target, td, files, target_path, execution.timeout, overwrite): td for td in target_details}
        for future in as_completed(futures):
            target_detail = futures[future]
            try:
                result = future.result()
                logger.info(f"[{task_name}] 目标 {target_detail.target.name} 分发完成: success={result['success']}")
            except Exception as e:
                logger.exception(f"[{task_name}] 目标 {target_detail.target.name} 分发异常: {e}")

    _finalize_execution(execution, task_name)


def _execute_playbook_on_target(target_detail: JobExecutionTarget, timeout: int) -> dict:
    """在单个目标上执行 Playbook

    Playbook 简化设计：直接执行 playbook.yml，无需额外参数
    注意：实际实现需要先下载 Playbook 压缩包到目标并解压
    """
    target = target_detail.target
    result = {
        "target_id": target.id,
        "success": False,
        "stdout": "",
        "stderr": "",
        "exit_code": None,
        "error_message": "",
    }

    started_at = timezone.now()
    _update_target_status(target_detail, ExecutionStatus.RUNNING, started_at=started_at)

    try:
        # 构建 ansible-playbook 命令
        # 注意：实际实现需要先下载 playbook 到本地，生成 inventory，然后执行
        # 这里为简化实现，假设 playbook 已在目标可访问的位置
        # 固定入口文件为 playbook.yml
        command = "ansible-playbook playbook.yml -i localhost, -c local"

        if target.source == TargetSource.SYNC:
            executor = Executor(target.node_id)
            exec_result = executor.execute_local(command, timeout=timeout, shell="bash")
        else:
            executor = Executor(target.node_id)
            exec_result = executor.execute_ssh(
                command=command,
                host=target.ip,
                username=target.ssh_user,
                password=target.ssh_password if target.ssh_password else None,
                private_key=_get_ssh_private_key(target),
                timeout=timeout,
                port=target.ssh_port,
            )

        result["stdout"] = exec_result.get("stdout", "")
        result["stderr"] = exec_result.get("stderr", "")
        result["exit_code"] = exec_result.get("exit_code", exec_result.get("code", -1))
        result["success"] = result["exit_code"] == 0

    except Exception as e:
        result["error_message"] = _format_error_message(e)
        result["stderr"] = result["error_message"]
        logger.exception(f"目标 {target.name}({target.ip}) Playbook执行失败")

    finished_at = timezone.now()
    status = ExecutionStatus.SUCCESS if result["success"] else ExecutionStatus.FAILED
    _update_target_status(
        target_detail,
        status,
        stdout=result["stdout"],
        stderr=result["stderr"],
        exit_code=result["exit_code"],
        error_message=result["error_message"],
        finished_at=finished_at,
    )

    return result


@shared_task(bind=True, max_retries=0)
def execute_playbook_task(self, execution_id: int):
    """
    Playbook 执行任务

    Args:
        execution_id: 作业执行记录ID

    注意：当前为简化实现。完整实现应该：
    1. 从 MinIO 下载 Playbook 压缩包
    2. 解压到临时目录
    3. 根据目标列表生成 inventory 文件
    4. 执行 ansible-playbook 命令
    5. 收集执行结果
    6. 清理临时文件
    """
    task_name = "execute_playbook_task"
    logger.info(f"[{task_name}] 开始执行Playbook任务: execution_id={execution_id}")

    execution, target_details = _prepare_execution(execution_id, task_name)
    if not execution:
        return

    # 检查 Playbook 是否存在
    if not execution.playbook:
        logger.error(f"[{task_name}] Playbook 不存在: execution_id={execution_id}")
        _update_execution_status(execution, ExecutionStatus.FAILED, finished_at=timezone.now())
        return

    # 并发执行
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(target_details))) as pool:
        futures = {pool.submit(_execute_playbook_on_target, td, execution.timeout): td for td in target_details}
        for future in as_completed(futures):
            target_detail = futures[future]
            try:
                result = future.result()
                logger.info(f"[{task_name}] 目标 {target_detail.target.name} 执行完成: success={result['success']}")
            except Exception as e:
                logger.exception(f"[{task_name}] 目标 {target_detail.target.name} 执行异常: {e}")

    _finalize_execution(execution, task_name)


@shared_task(bind=True, max_retries=0)
def execute_scheduled_task(self, scheduled_task_id: int):
    """
    定时任务触发执行

    由 Celery Beat 调用，根据定时任务配置创建 JobExecution 并执行

    Args:
        scheduled_task_id: 定时任务ID
    """
    from apps.job_mgmt.constants import JobType
    from apps.job_mgmt.models import ScheduledTask

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

    # 获取执行目标
    targets = list(scheduled_task.targets.all())
    if not targets:
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
        total_count=len(targets),
        team=scheduled_task.team,
        created_by=scheduled_task.created_by,
        updated_by=scheduled_task.updated_by,
    )

    # 创建 JobExecutionTarget
    for target in targets:
        JobExecutionTarget.objects.create(
            execution=execution,
            target=target,
            status=ExecutionStatus.PENDING,
        )

    logger.info(f"[execute_scheduled_task] 创建执行记录: execution_id={execution.id}, targets={len(targets)}")

    # 根据作业类型调用对应的执行任务
    if scheduled_task.job_type == JobType.SCRIPT:
        execute_script_task.delay(execution.id)
    elif scheduled_task.job_type == JobType.FILE_DISTRIBUTION:
        distribute_files_task.delay(execution.id)
    elif scheduled_task.job_type == JobType.PLAYBOOK:
        execute_playbook_task.delay(execution.id)
    else:
        logger.error(f"[execute_scheduled_task] 未知的作业类型: {scheduled_task.job_type}")
        execution.status = ExecutionStatus.FAILED
        execution.save(update_fields=["status", "updated_at"])
        return

    logger.info(f"[execute_scheduled_task] 定时任务触发完成: scheduled_task_id={scheduled_task_id}, execution_id={execution.id}")


@shared_task(bind=True, max_retries=0)
def sync_targets_from_nodes_task(self, node_ids: list = None, team: list = None):
    """
    后台同步 Node 到 Target

    由 Celery 异步执行，避免同步时间过长导致接口超时

    Args:
        node_ids: 要同步的 Node ID 列表，为空则同步全部
        team: 目标归属团队 ID 列表
    """
    from apps.job_mgmt.services.target_sync import TargetSyncService

    logger.info(f"[sync_targets_from_nodes_task] 开始同步: node_ids={node_ids}, team={team}")

    try:
        service = TargetSyncService()
        result = service.sync_nodes(node_ids=node_ids, team=team)
        logger.info(f"[sync_targets_from_nodes_task] 同步完成: created={result['created']}, updated={result['updated']}, skipped={result['skipped']}")
    except Exception as e:
        logger.exception(f"[sync_targets_from_nodes_task] 同步失败: {e}")
