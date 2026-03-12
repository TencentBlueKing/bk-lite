"""作业执行 Celery 任务

执行逻辑根据 JobExecution.target_source 字段选择不同的执行方式：
- target_source=node_mgmt: 使用 execute_local / download_to_local（通过 node_id 定位 Sidecar）
- target_source=manual: 使用 execute_ssh / download_to_remote（通过 SSH 凭据连接）
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional, Tuple

from asgiref.sync import async_to_sync
from celery import shared_task
from django.utils import timezone

from apps.core.logger import job_logger as logger
from apps.job_mgmt.constants import ExecutionStatus, ScriptType, TargetSource
from apps.job_mgmt.models import JobExecution, Target
from apps.job_mgmt.services.dangerous_checker import DangerousChecker
from apps.job_mgmt.services.script_params_service import ScriptParamsService
from apps.node_mgmt.utils.s3 import delete_s3_file
from apps.rpc.executor import Executor
from config.components.nats import NATS_NAMESPACE

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
    """更新执行统计（从 execution_results 中计算）"""
    results = execution.execution_results or []
    execution.success_count = sum(1 for r in results if r.get("status") == ExecutionStatus.SUCCESS)
    execution.failed_count = sum(1 for r in results if r.get("status") in [ExecutionStatus.FAILED, ExecutionStatus.TIMEOUT])
    execution.save(update_fields=["success_count", "failed_count", "updated_at"])


def _get_shell_type(script_type: str) -> str:
    """获取 shell 类型映射"""
    return ScriptType.SHELL_MAPPING.get(script_type, "sh")


def _get_ssh_credentials(target_id: int) -> dict:
    """从 Target 获取 SSH 凭据信息"""
    try:
        target = Target.objects.get(id=target_id)
        private_key = None
        if target.ssh_key_file:
            try:
                target.ssh_key_file.open("r")
                content = target.ssh_key_file.read()
                target.ssh_key_file.close()
                if isinstance(content, bytes):
                    private_key = content.decode("utf-8")
                else:
                    private_key = content
            except Exception:
                pass
        return {
            "host": target.ip,
            "username": target.ssh_user,
            "password": target.ssh_password if target.ssh_password else None,
            "private_key": private_key,
            "port": target.ssh_port,
            "node_id": target.node_id,  # 云区域 ID
        }
    except Target.DoesNotExist:
        return {}


def _prepare_execution(execution_id: int, task_name: str) -> Tuple[Optional[JobExecution], list]:
    """
    任务执行前置处理

    Returns:
        (execution, target_list): 成功时返回执行记录和目标列表
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

    # 获取目标列表
    target_list = execution.target_list or []

    if not target_list:
        logger.warning(f"[{task_name}] 无待执行目标: execution_id={execution_id}")
        _update_execution_status(execution, ExecutionStatus.SUCCESS, finished_at=timezone.now())
        return None, []

    return execution, target_list


def _finalize_execution(execution: JobExecution, task_name: str, results: list):
    """任务执行后置处理：保存结果、刷新状态、统计、确定最终结果"""
    # 保存执行结果
    execution.execution_results = results
    execution.save(update_fields=["execution_results", "updated_at"])

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


def _execute_script_on_target(target_info: dict, target_source: str, script_content: str, script_type: str, timeout: int) -> dict:
    """在单个目标上执行脚本

    Args:
        target_info: 目标信息字典
            - node_mgmt: {"node_id": "xxx", "name": "xxx", "ip": "1.2.3.4", "os": "linux", "cloud_region_id": 1}
            - manual: {"target_id": 1, "name": "xxx", "ip": "1.2.3.4"}
        target_source: 目标来源 (node_mgmt / manual)
        script_content: 脚本内容
        script_type: 脚本类型
        timeout: 超时时间
    """
    # 确定 target_key（用于结果标识）
    target_key = target_info.get("node_id") or str(target_info.get("target_id", ""))
    target_name = target_info.get("name", "")
    target_ip = target_info.get("ip", "")

    result = {
        "target_key": target_key,
        "name": target_name,
        "ip": target_ip,
        "status": ExecutionStatus.PENDING,
        "stdout": "",
        "stderr": "",
        "exit_code": None,
        "error_message": "",
        "started_at": timezone.now().isoformat(),
        "finished_at": "",
    }

    try:
        shell = _get_shell_type(script_type)

        if target_source in (TargetSource.NODE_MGMT, TargetSource.SYNC):
            # 节点管理来源：使用 execute_local，node_id 是 Sidecar 实例 ID
            node_id = target_info.get("node_id")
            executor = Executor(node_id)
            logger.info(f"kwargs: {node_id}")
            exec_result = executor.execute_local(script_content, timeout=timeout, shell=shell)
            logger.info(f"exec_result: {exec_result}")
        else:
            # 手动来源：使用 execute_ssh，需要从 Target 获取凭据
            target_id = target_info.get("target_id")
            ssh_creds = _get_ssh_credentials(target_id)
            if not ssh_creds:
                raise ValueError(f"无法获取目标凭据: target_id={target_id}")

            executor = Executor(ssh_creds["node_id"])  # 云区域 ID
            exec_result = executor.execute_ssh(
                command=script_content,
                host=ssh_creds["host"],
                username=ssh_creds["username"],
                password=ssh_creds["password"],
                private_key=ssh_creds["private_key"],
                timeout=timeout,
                port=ssh_creds["port"],
            )

        # 解析执行结果
        if isinstance(exec_result, str):
            result["stdout"] = exec_result
            result["stderr"] = ""
            result["exit_code"] = 0
            result["status"] = ExecutionStatus.SUCCESS
        elif isinstance(exec_result, dict):
            result["stdout"] = exec_result.get("stdout", exec_result.get("result", ""))
            result["stderr"] = exec_result.get("stderr", "")
            result["exit_code"] = exec_result.get("exit_code", exec_result.get("code", 0))
            result["status"] = ExecutionStatus.SUCCESS if result["exit_code"] == 0 else ExecutionStatus.FAILED
        else:
            result["stdout"] = str(exec_result)
            result["stderr"] = ""
            result["exit_code"] = 0
            result["status"] = ExecutionStatus.SUCCESS

    except Exception as e:
        result["error_message"] = _format_error_message(e)
        result["stderr"] = result["error_message"]
        result["status"] = ExecutionStatus.FAILED
        logger.exception(f"目标 {target_name}({target_ip}) 脚本执行失败")

    result["finished_at"] = timezone.now().isoformat()
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

    execution, target_list = _prepare_execution(execution_id, task_name)
    if not execution:
        return

    # 高危命令检测（周期任务期间可能新增规则）
    check_result = DangerousChecker.check_command(execution.script_content, execution.team)
    if not check_result.can_execute:
        forbidden_rules = [r["rule_name"] for r in check_result.forbidden]
        error_msg = f"检测到高危命令，禁止执行: {', '.join(forbidden_rules)}"
        logger.warning(f"[{task_name}] {error_msg}")
        _update_execution_status(execution, ExecutionStatus.FAILED, finished_at=timezone.now())
        # 记录错误到 execution_results
        error_results = [
            {
                "target_key": t.get("node_id") or str(t.get("target_id", "")),
                "name": t.get("name", ""),
                "ip": t.get("ip", ""),
                "status": ExecutionStatus.FAILED,
                "error_message": error_msg,
            }
            for t in target_list
        ]
        execution.execution_results = error_results
        execution.save(update_fields=["execution_results", "updated_at"])
        return

    # 获取脚本内容
    script_content = execution.script_content
    script_type = execution.script_type

    # 如果有命令行参数，附加到脚本内容末尾
    if execution.params:
        script_content = f"{script_content} {execution.params}"

    # 并发执行
    results = []
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(target_list))) as pool:
        futures = {
            pool.submit(_execute_script_on_target, t, execution.target_source, script_content, script_type, execution.timeout): t for t in target_list
        }
        for future in as_completed(futures):
            target_info = futures[future]
            try:
                result = future.result()
                results.append(result)
                logger.info(f"[{task_name}] 目标 {target_info.get('name')} 执行完成: status={result['status']}")
            except Exception as e:
                logger.exception(f"[{task_name}] 目标 {target_info.get('name')} 执行异常: {e}")
                # 记录失败结果
                results.append(
                    {
                        "target_key": target_info.get("node_id") or str(target_info.get("target_id", "")),
                        "name": target_info.get("name", ""),
                        "ip": target_info.get("ip", ""),
                        "status": ExecutionStatus.FAILED,
                        "error_message": str(e),
                    }
                )

    _finalize_execution(execution, task_name, results)


def _distribute_file_to_target(target_info: dict, target_source: str, files: list, target_path: str, timeout: int, overwrite: bool = True) -> dict:
    """分发文件到单个目标

    Args:
        target_info: 目标信息字典
        target_source: 目标来源 (node_mgmt / manual)
        files: 文件列表
        target_path: 目标路径
        timeout: 超时时间
        overwrite: 是否覆盖
    """
    target_key = target_info.get("node_id") or str(target_info.get("target_id", ""))
    target_name = target_info.get("name", "")
    target_ip = target_info.get("ip", "")

    result = {
        "target_key": target_key,
        "name": target_name,
        "ip": target_ip,
        "status": ExecutionStatus.PENDING,
        "stdout": "",
        "stderr": "",
        "exit_code": None,
        "error_message": "",
        "file_results": [],
        "started_at": timezone.now().isoformat(),
        "finished_at": "",
    }

    success = True
    try:
        for file_item in files:
            file_result = {"file_name": file_item.get("name", ""), "success": False, "error": ""}

            try:
                if target_source in (TargetSource.NODE_MGMT, TargetSource.SYNC):
                    # 节点管理来源：使用 download_to_local
                    node_id = target_info.get("node_id")
                    executor = Executor(node_id)
                    params = dict(
                        bucket_name=NATS_NAMESPACE,
                        file_key=file_item.get("file_key", ""),
                        file_name=file_item.get("name", ""),
                        target_path=target_path,
                        timeout=timeout,
                        overwrite=overwrite,
                    )
                    exec_result = executor.download_to_local(**params)
                else:
                    # 手动来源：使用 download_to_remote
                    target_id = target_info.get("target_id")
                    ssh_creds = _get_ssh_credentials(target_id)
                    if not ssh_creds:
                        raise ValueError(f"无法获取目标凭据: target_id={target_id}")

                    executor = Executor(ssh_creds["node_id"])
                    exec_result = executor.download_to_remote(
                        bucket_name=NATS_NAMESPACE,
                        file_key=file_item.get("file_key", ""),
                        file_name=file_item.get("name", ""),
                        target_path=target_path,
                        host=ssh_creds["host"],
                        username=ssh_creds["username"],
                        password=ssh_creds["password"],
                        private_key=ssh_creds["private_key"],
                        timeout=timeout,
                        port=ssh_creds["port"],
                        overwrite=overwrite,
                    )

                # 检查结果
                if isinstance(exec_result, str):
                    if "successfully" in exec_result.lower() or "success" in exec_result.lower():
                        file_result["success"] = True
                    else:
                        file_result["error"] = exec_result
                        success = False
                elif isinstance(exec_result, dict):
                    if exec_result.get("code", -1) == 0 or exec_result.get("success", False):
                        file_result["success"] = True
                    else:
                        file_result["error"] = exec_result.get("message", exec_result.get("stderr", "未知错误"))
                        success = False
                else:
                    file_result["error"] = f"未知响应类型: {type(exec_result)}"
                    success = False

            except Exception as e:
                file_result["error"] = str(e)
                success = False
                logger.exception(f"文件 {file_item.get('name')} 分发到 {target_name} 失败")

            result["file_results"].append(file_result)

    except Exception as e:
        success = False
        result["error_message"] = f"分发异常: {str(e)}"
        logger.exception(f"目标 {target_name}({target_ip}) 文件分发失败")

    # 汇总错误信息
    errors = [f"{fr['file_name']}: {fr['error']}" for fr in result["file_results"] if not fr["success"]]
    error_message = "\n".join(errors) if errors else result.get("error_message", "")

    result["status"] = ExecutionStatus.SUCCESS if success else ExecutionStatus.FAILED
    result["stdout"] = f"分发 {len(files)} 个文件到 {target_path}"
    result["stderr"] = error_message
    result["exit_code"] = 0 if success else 1
    result["error_message"] = error_message
    result["finished_at"] = timezone.now().isoformat()

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

    execution, target_list = _prepare_execution(execution_id, task_name)
    if not execution:
        return

    # 高危路径检测（周期任务期间可能新增规则）
    check_result = DangerousChecker.check_path(execution.target_path, execution.team)
    if not check_result.can_execute:
        forbidden_rules = [r["rule_name"] for r in check_result.forbidden]
        error_msg = f"目标路径为高危路径，禁止分发: {', '.join(forbidden_rules)}"
        logger.warning(f"[{task_name}] {error_msg}")
        _update_execution_status(execution, ExecutionStatus.FAILED, finished_at=timezone.now())
        # 记录错误到 execution_results
        error_results = [
            {
                "target_key": t.get("node_id") or str(t.get("target_id", "")),
                "name": t.get("name", ""),
                "ip": t.get("ip", ""),
                "status": ExecutionStatus.FAILED,
                "error_message": error_msg,
            }
            for t in target_list
        ]
        execution.execution_results = error_results
        execution.save(update_fields=["execution_results", "updated_at"])
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
    results = []
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(target_list))) as pool:
        futures = {
            pool.submit(_distribute_file_to_target, t, execution.target_source, files, target_path, execution.timeout, overwrite): t
            for t in target_list
        }
        for future in as_completed(futures):
            target_info = futures[future]
            try:
                result = future.result()
                results.append(result)
                logger.info(f"[{task_name}] 目标 {target_info.get('name')} 分发完成: status={result['status']}")
            except Exception as e:
                logger.exception(f"[{task_name}] 目标 {target_info.get('name')} 分发异常: {e}")
                results.append(
                    {
                        "target_key": target_info.get("node_id") or str(target_info.get("target_id", "")),
                        "name": target_info.get("name", ""),
                        "ip": target_info.get("ip", ""),
                        "status": ExecutionStatus.FAILED,
                        "error_message": str(e),
                    }
                )

    _finalize_execution(execution, task_name, results)


def _execute_playbook_on_target(target_info: dict, target_source: str, timeout: int) -> dict:
    """在单个目标上执行 Playbook

    Playbook 简化设计：直接执行 playbook.yml，无需额外参数
    注意：实际实现需要先下载 Playbook 压缩包到目标并解压

    Args:
        target_info: 目标信息字典
        target_source: 目标来源 (node_mgmt / manual)
        timeout: 超时时间
    """
    target_key = target_info.get("node_id") or str(target_info.get("target_id", ""))
    target_name = target_info.get("name", "")
    target_ip = target_info.get("ip", "")

    result = {
        "target_key": target_key,
        "name": target_name,
        "ip": target_ip,
        "status": ExecutionStatus.PENDING,
        "stdout": "",
        "stderr": "",
        "exit_code": None,
        "error_message": "",
        "started_at": timezone.now().isoformat(),
        "finished_at": "",
    }

    try:
        # 构建 ansible-playbook 命令
        command = "ansible-playbook playbook.yml -i localhost, -c local"

        if target_source in (TargetSource.NODE_MGMT, TargetSource.SYNC):
            node_id = target_info.get("node_id")
            executor = Executor(node_id)
            exec_result = executor.execute_local(command, timeout=timeout, shell="bash")
        else:
            target_id = target_info.get("target_id")
            ssh_creds = _get_ssh_credentials(target_id)
            if not ssh_creds:
                raise ValueError(f"无法获取目标凭据: target_id={target_id}")

            executor = Executor(ssh_creds["node_id"])
            exec_result = executor.execute_ssh(
                command=command,
                host=ssh_creds["host"],
                username=ssh_creds["username"],
                password=ssh_creds["password"],
                private_key=ssh_creds["private_key"],
                timeout=timeout,
                port=ssh_creds["port"],
            )

        if isinstance(exec_result, dict):
            result["stdout"] = exec_result.get("stdout", "")
            result["stderr"] = exec_result.get("stderr", "")
            result["exit_code"] = exec_result.get("exit_code", exec_result.get("code", -1))
            result["status"] = ExecutionStatus.SUCCESS if result["exit_code"] == 0 else ExecutionStatus.FAILED
        else:
            result["stdout"] = str(exec_result)
            result["exit_code"] = 0
            result["status"] = ExecutionStatus.SUCCESS

    except Exception as e:
        result["error_message"] = _format_error_message(e)
        result["stderr"] = result["error_message"]
        result["status"] = ExecutionStatus.FAILED
        logger.exception(f"目标 {target_name}({target_ip}) Playbook执行失败")

    result["finished_at"] = timezone.now().isoformat()
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

    execution, target_list = _prepare_execution(execution_id, task_name)
    if not execution:
        return

    # 检查 Playbook 是否存在
    if not execution.playbook:
        logger.error(f"[{task_name}] Playbook 不存在: execution_id={execution_id}")
        _update_execution_status(execution, ExecutionStatus.FAILED, finished_at=timezone.now())
        return

    # 并发执行
    results = []
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(target_list))) as pool:
        futures = {pool.submit(_execute_playbook_on_target, t, execution.target_source, execution.timeout): t for t in target_list}
        for future in as_completed(futures):
            target_info = futures[future]
            try:
                result = future.result()
                results.append(result)
                logger.info(f"[{task_name}] 目标 {target_info.get('name')} 执行完成: status={result['status']}")
            except Exception as e:
                logger.exception(f"[{task_name}] 目标 {target_info.get('name')} 执行异常: {e}")
                results.append(
                    {
                        "target_key": target_info.get("node_id") or str(target_info.get("target_id", "")),
                        "name": target_info.get("name", ""),
                        "ip": target_info.get("ip", ""),
                        "status": ExecutionStatus.FAILED,
                        "error_message": str(e),
                    }
                )

    _finalize_execution(execution, task_name, results)


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
def cleanup_expired_distribution_files_task(self):
    """
    清理过期的分发文件

    删除 7 天前上传的临时文件，包括：
    - JetStream Object Store 中的文件
    - 数据库中的记录

    定时任务配置：每天 02:00 执行
    """
    from datetime import timedelta

    from apps.job_mgmt.models import DistributionFile

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
