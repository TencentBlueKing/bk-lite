from datetime import datetime
from typing import Optional, Tuple

from django.db import transaction
from django.utils import timezone

from apps.core.logger import job_logger as logger
from apps.core.mixinx import EncryptMixin
from apps.job_mgmt.config import EXECUTION_MAX_WORKERS
from apps.job_mgmt.constants import CredentialSource, ExecutionStatus, ExecutorDriver, OSType, ScriptType, SSHCredentialType, TargetSource
from apps.job_mgmt.models import JobExecution, Target
from apps.job_mgmt.services.callback_service import send_callback
from apps.job_mgmt.services.execution_stream_service import build_stream_topic
from apps.job_mgmt.services.shell_utils import ANSIBLE_SHELL_EXECUTABLES, build_heredoc_command, parse_shebang
from apps.rpc.ansible import AnsibleExecutor
from apps.rpc.node_mgmt import NodeMgmt
from apps.rpc.sensitive import sanitize_sensitive_data
from config.components.nats import NATS_NAMESPACE


class ExecutionTaskBaseService(object):
    MAX_WORKERS = EXECUTION_MAX_WORKERS

    def __init__(self, execution_id: int, task_name: str):
        self.execution_id = execution_id
        self.task_name = task_name

    @staticmethod
    def normalize_script_line_endings(script_content: str, script_type: str) -> str:
        """规范化脚本换行符（CRLF/CR -> LF）。

        Windows 编辑/粘贴的脚本常带 ``\\r\\n``，会让 Linux 的 bash/sh 报
        ``syntax error near unexpected token $'\\r'``；老 Mac 的裸 ``\\r`` 同理。
        类 Unix 脚本统一转 LF；Windows 原生脚本(bat/powershell)保持原样。

        sidecar(SSH/local_stream) 与 Ansible 两条下发路径都必须调用，缺一不可
        （#3404：dd4508928 只覆盖了 sidecar，遗漏 Ansible 路径）。
        """
        if not script_content or script_type in (ScriptType.BAT, ScriptType.POWERSHELL):
            return script_content
        return script_content.replace("\r\n", "\n").replace("\r", "\n")

    @staticmethod
    def decrypt_password(password: Optional[str]) -> Optional[str]:
        """解密密码字段（兼容历史明文数据）"""
        if not password:
            return None
        data = {"password": password}
        EncryptMixin.decrypt_field("password", data)
        return data.get("password")

    def prepare_execution(self) -> Tuple[Optional[JobExecution], list]:
        try:
            execution = JobExecution.objects.get(id=self.execution_id)
        except JobExecution.DoesNotExist:
            logger.error(f"[{self.task_name}] 执行记录不存在: execution_id={self.execution_id}")
            return None, []

        if execution.status == ExecutionStatus.CANCELLED:
            logger.info(f"[{self.task_name}] 任务已取消: execution_id={self.execution_id}")
            return None, []

        self.update_execution_status(execution, ExecutionStatus.RUNNING, started_at=timezone.now())
        target_list = execution.target_list or []
        if not target_list:
            logger.warning(f"[{self.task_name}] 无待执行目标: execution_id={self.execution_id}")
            self.update_execution_status(execution, ExecutionStatus.SUCCESS, finished_at=timezone.now())
            return None, []
        return execution, target_list

    @staticmethod
    def build_target_failed_result(target_info: dict, error_message: str) -> dict:
        return {
            "target_key": target_info.get("node_id") or str(target_info.get("target_id", "")),
            "name": target_info.get("name", ""),
            "ip": target_info.get("ip", ""),
            "status": ExecutionStatus.FAILED,
            "error_message": error_message,
        }

    @staticmethod
    def update_execution_status(
        execution: JobExecution,
        status: str,
        started_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None,
    ):
        update_fields = ["status", "updated_at"]
        execution.status = status
        if started_at:
            execution.started_at = started_at
            update_fields.append("started_at")
        if finished_at:
            execution.finished_at = finished_at
            update_fields.append("finished_at")
        execution.save(update_fields=update_fields)

    @staticmethod
    def is_cancelled(execution_id: int) -> bool:
        """从数据库刷新并检查执行是否已被取消"""
        try:
            current_status = JobExecution.objects.filter(id=execution_id).values_list("status", flat=True).first()
            return current_status == ExecutionStatus.CANCELLED
        except Exception:
            return False

    @staticmethod
    def update_execution_counts(execution: JobExecution):
        """重算 success_count / failed_count 并保存。

        在事务内对当前 execution 行加 ``SELECT ... FOR UPDATE`` 锁，
        消除"读 execution_results → 计数 → 写 counts"窗口内的并发覆盖。
        计算后回写到传入的 ``execution`` 实例，保证调用方读到的字段值是最新的。
        """
        with transaction.atomic():
            locked = JobExecution.objects.select_for_update().get(id=execution.id)
            results = locked.execution_results or []
            success_count = sum(1 for r in results if r.get("status") == ExecutionStatus.SUCCESS)
            failed_count = sum(1 for r in results if r.get("status") in [ExecutionStatus.FAILED, ExecutionStatus.TIMEOUT])
            locked.success_count = success_count
            locked.failed_count = failed_count
            locked.save(update_fields=["success_count", "failed_count", "updated_at"])
        execution.success_count = success_count
        execution.failed_count = failed_count

    @classmethod
    def finalize_execution(cls, execution: JobExecution, task_name: str, results: list):
        execution.execution_results = results
        execution.save(update_fields=["execution_results", "updated_at"])
        execution.refresh_from_db()
        if execution.status == ExecutionStatus.CANCELLED:
            # 取消时仍保留已完成的结果和计数，但状态保持 CANCELLED
            cls.update_execution_counts(execution)
            execution.finished_at = timezone.now()
            execution.save(update_fields=["finished_at", "updated_at"])
            logger.info(
                f"[{task_name}] 任务被取消，保留已完成结果: execution_id={execution.id}, " f"success={execution.success_count}, failed={execution.failed_count}"
            )
            # 取消时也发送回调通知，让第三方系统知道任务被取消
            execution.refresh_from_db()
            send_callback(execution)
            return
        cls.update_execution_counts(execution)
        final_status = ExecutionStatus.FAILED if execution.failed_count > 0 else ExecutionStatus.SUCCESS
        cls.update_execution_status(execution, final_status, finished_at=timezone.now())
        logger.info(f"[{task_name}] 任务完成: execution_id={execution.id}, status={final_status}")

        # 回调通知（如有 callback_url）
        execution.refresh_from_db()
        send_callback(execution)

    @staticmethod
    def _should_use_ansible(target_source: str, target_list: list) -> bool:
        """
        判断是否应使用 Ansible 执行

        Args:
            target_source: 目标来源
            target_list: 目标列表

        Returns:
            True 如果应使用 Ansible 执行
        """
        if target_source != TargetSource.MANUAL:
            return False

        # 检查第一个目标的驱动类型
        target_ids = [t.get("target_id") for t in target_list if t.get("target_id")]
        if not target_ids:
            return False

        target = Target.objects.filter(id=target_ids[0]).first()
        if not target:
            return False

        return target.driver == ExecutorDriver.ANSIBLE

    @classmethod
    def _get_manual_targets(cls, target_list: list) -> list:
        target_ids = [t.get("target_id") for t in target_list if t.get("target_id")]
        if not target_ids:
            return []
        return list(Target.objects.filter(id__in=target_ids))

    @classmethod
    def _contains_windows_manual_target(cls, target_list: list) -> bool:
        return any(target.os_type == OSType.WINDOWS for target in cls._get_manual_targets(target_list))

    @classmethod
    def _execute_script_via_ansible(cls, execution: JobExecution, target_list: list, script_content: str, script_type: str) -> None:
        """
        通过 Ansible 执行脚本（异步方式）

        对于手动目标且使用 Ansible 驱动的情况，调用 Ansible Executor 执行脚本。
        执行结果通过 NATS 回调返回。

        Args:
            execution: 作业执行记录
            target_list: 目标列表（包含 target_id）
            script_content: 脚本内容
            script_type: 脚本类型
        """
        task_name = "execute_script_via_ansible"

        # 规范化换行符：与 sidecar 路径一致，类 Unix 脚本转 LF（#3404）
        script_content = cls.normalize_script_line_endings(script_content, script_type)

        # 获取所有目标的 Target 对象
        target_ids = [t.get("target_id") for t in target_list if t.get("target_id")]
        if not target_ids:
            raise ValueError("未找到有效的目标ID")

        targets = list(Target.objects.filter(id__in=target_ids))
        if not targets:
            raise ValueError("未找到有效的目标记录")

        # 按云区域分组目标
        region_targets = {}
        for target in targets:
            region_id = target.cloud_region_id
            if region_id not in region_targets:
                region_targets[region_id] = []
            region_targets[region_id].append(target)

        # 目前只支持单云区域执行，取第一个云区域
        if len(region_targets) > 1:
            logger.warning(f"[{task_name}] 检测到多个云区域，当前仅使用第一个云区域执行")

        cloud_region_id = list(region_targets.keys())[0]
        region_target_list = region_targets[cloud_region_id]

        # 获取 Ansible 执行节点
        try:
            ansible_node_id = cls._get_ansible_node(cloud_region_id)
        except ValueError as e:
            raise ValueError(f"获取 Ansible 节点失败: {e}")

        # 构建凭据
        host_credentials = cls._build_host_credentials(region_target_list)

        # 构建回调配置
        callback_config = {
            "subject": f"{NATS_NAMESPACE}.ansible_task_callback",
            "timeout": 30,
        }

        # 根据脚本类型选择模块
        shell_mapping = {
            ScriptType.SHELL: "shell",
            ScriptType.PYTHON: "shell",
            ScriptType.POWERSHELL: "win_shell",
            ScriptType.BAT: "win_shell",
        }
        module = shell_mapping.get(script_type, "shell")

        shell_interpreter = parse_shebang(script_content) or ScriptType.SHELL_MAPPING.get(script_type, "bash")
        module_args = script_content

        # Linux shell 模块：sh/bash 走 ansible_shell_executable，其他解释器走 heredoc 包装
        extra_vars = {}
        if module == "shell":
            if shell_interpreter in ANSIBLE_SHELL_EXECUTABLES:
                extra_vars["ansible_shell_executable"] = f"/bin/{shell_interpreter}"
            else:
                module_args = build_heredoc_command(shell_interpreter, script_content)

        # 调用 Ansible Executor
        executor = AnsibleExecutor(ansible_node_id)
        result = executor.adhoc(
            host_credentials=host_credentials,
            module=module,
            module_args=module_args,
            callback=callback_config,
            task_id=str(execution.id),
            timeout=execution.timeout,
            extra_vars=extra_vars if extra_vars else None,
            stream_log_topic=build_stream_topic(execution.id, "ansible"),
            execution_id=str(execution.id),
        )

        logger.info(f"[{task_name}] Ansible 任务已提交: execution_id={execution.id}, result={sanitize_sensitive_data(result)}")

    @staticmethod
    def _get_ansible_node(cloud_region_id: int) -> str:
        """
        根据云区域ID获取 Ansible 执行节点

        Args:
            cloud_region_id: 云区域ID

        Returns:
            节点ID

        Raises:
            ValueError: 未找到可用的 Ansible 执行节点
        """
        node_mgmt = NodeMgmt()
        result = node_mgmt.node_list({"cloud_region_id": cloud_region_id, "is_container": True, "page": 1, "page_size": 1, "skip_permission": True})
        if not isinstance(result, dict):
            raise ValueError(f"云区域 {cloud_region_id} 下未找到可用的 Ansible 执行节点")
        nodes = result.get("nodes", [])
        if not nodes:
            raise ValueError(f"云区域 {cloud_region_id} 下未找到可用的 Ansible 执行节点")
        return nodes[0]["id"]

    @classmethod
    def _build_host_credentials(cls, targets: list) -> list:
        """
        构建多主机凭据列表

        Args:
            targets: Target 对象列表

        Returns:
            host_credentials 列表，每个元素包含主机连接信息
        """
        credentials = []
        for target in targets:
            # 凭据来源检查：credential 模式暂未实现，记录警告并跳过
            if target.credential_source == CredentialSource.CREDENTIAL:
                logger.warning(f"[_build_host_credentials] 目标 {target.ip} 使用凭据管理(credential_id={target.credential_id})，该模式暂未实现，跳过此目标")
                continue

            cred = {
                "host": target.ip,
                "port": target.ssh_port if target.os_type == OSType.LINUX else target.winrm_port,
            }

            if target.os_type == OSType.LINUX:
                cred["user"] = target.ssh_user
                cred["connection"] = "ssh"
                if target.ssh_credential_type == SSHCredentialType.PASSWORD:
                    cred["password"] = cls.decrypt_password(target.ssh_password)
                else:
                    private_key = cls._read_ssh_key_file(target)
                    if private_key:
                        cred["private_key_content"] = private_key
                    ssh_key_passphrase = cls.decrypt_password(target.ssh_key_passphrase)
                    if ssh_key_passphrase:
                        cred["private_key_passphrase"] = ssh_key_passphrase
            else:
                # Windows
                cred["user"] = target.winrm_user
                cred["password"] = cls.decrypt_password(target.winrm_password)
                cred["connection"] = "winrm"
                cred["winrm_scheme"] = target.winrm_scheme
                cred["winrm_transport"] = target.winrm_transport
                cred["winrm_cert_validation"] = target.winrm_cert_validation

            credentials.append(cred)
        return credentials

    @staticmethod
    def _read_ssh_key_file(target) -> Optional[str]:
        """读取 Target 的 SSH 私钥文件内容；读取失败返回 None 并记录告警。

        使用上下文管理器确保异常路径也能释放文件句柄；仅捕获文件 / IO 类异常，
        避免静默吞掉非预期错误（原实现 except Exception 会掩盖权限 / IO 问题）。
        """
        if not target.ssh_key_file:
            return None
        try:
            with target.ssh_key_file.open("r") as fh:
                content = fh.read()
        except (FileNotFoundError, OSError) as e:
            logger.warning(f"[_read_ssh_key_file] 读取 SSH 密钥文件失败: target_id={getattr(target, 'id', None)}, error={e}")
            return None
        return content.decode("utf-8") if isinstance(content, bytes) else content

    @classmethod
    def get_ssh_credentials(cls, target_id: int) -> dict:
        """从 Target 获取 SSH 凭据信息"""
        try:
            target = Target.objects.get(id=target_id)
        except Target.DoesNotExist:
            return {}
        return {
            "host": target.ip,
            "username": target.ssh_user,
            "password": cls.decrypt_password(target.ssh_password),
            "private_key": cls._read_ssh_key_file(target),
            "port": target.ssh_port,
            "node_id": target.node_id,  # 云区域 ID
        }

    @staticmethod
    def format_error_message(e: Exception) -> str:
        """格式化异常信息，提取关键内容"""
        error_str = str(e)
        error_type = type(e).__name__

        # 提取常见关键字
        keywords = ["timeout", "connection", "refused", "denied", "permission", "authentication", "unreachable", "reset"]
        hints = [kw for kw in keywords if kw.lower() in error_str.lower()]

        if hints:
            return f"执行过程出错: {error_type} ({', '.join(hints)})"
        return f"执行过程出错: {error_type} - {error_str[:200]}" if len(error_str) > 200 else f"执行过程出错: {error_type} - {error_str}"

    @staticmethod
    def normalize_executor_error(exec_result, default_message: str = "执行失败") -> str:
        """将执行器返回的错误统一映射为更友好的中文文案"""
        if isinstance(exec_result, str):
            raw_message = exec_result
            code = ""
            stage = ""
            category = ""
        elif isinstance(exec_result, dict):
            raw_message = str(exec_result.get("error") or exec_result.get("stderr") or exec_result.get("message") or exec_result.get("result") or "")
            code = str(exec_result.get("code") or "")
            stage = str(exec_result.get("stage") or "")
            category = str(exec_result.get("category") or "")
        else:
            return default_message

        message = raw_message.strip()
        if stage == "tcp_connect":
            return f"目标地址或端口不可达，请检查网络连通性和端口是否开放：{message or default_message}"
        if stage == "ssh_dial" and category == "network":
            return f"SSH连接超时或网络异常，请检查目标主机网络和端口连通性：{message or default_message}"
        if stage == "ssh_dial" and category == "auth":
            return f"SSH认证失败，请检查用户名、密码或私钥是否正确：{message or default_message}"
        if stage == "legacy_retry" and category == "compatibility":
            return f"SSH协议兼容性失败，请检查目标主机SSH算法配置：{message or default_message}"
        if stage == "session_create":
            return f"SSH会话创建失败，请检查目标主机SSH服务状态：{message or default_message}"
        if stage == "command_run" and category == "remote_timeout":
            return f"远程命令执行超时：{message or default_message}"
        if stage == "command_run" and category == "remote_exit":
            return f"远程命令执行失败：{message or default_message}"
        if code == "timeout":
            return f"执行超时：{message or default_message}"
        if message:
            return message
        return default_message
