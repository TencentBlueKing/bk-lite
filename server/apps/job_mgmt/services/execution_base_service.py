from datetime import datetime
from typing import Optional, Tuple

from django.utils import timezone

from apps.core.logger import job_logger as logger
from apps.core.mixinx import EncryptMixin
from apps.job_mgmt.constants import ExecutionStatus, ExecutorDriver, OSType, ScriptType, SSHCredentialType, TargetSource
from apps.job_mgmt.models import JobExecution, Target
from apps.rpc.ansible import AnsibleExecutor
from apps.rpc.node_mgmt import NodeMgmt
from config.components.nats import NATS_NAMESPACE


class ExecutionTaskBaseService(object):
    MAX_WORKERS = 10

    def __init__(self, execution_id: int, task_name: str):
        self.execution_id = execution_id
        self.task_name = task_name

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
    def update_execution_counts(execution: JobExecution):
        results = execution.execution_results or []
        execution.success_count = sum(1 for r in results if r.get("status") == ExecutionStatus.SUCCESS)
        execution.failed_count = sum(1 for r in results if r.get("status") in [ExecutionStatus.FAILED, ExecutionStatus.TIMEOUT])
        execution.save(update_fields=["success_count", "failed_count", "updated_at"])

    @classmethod
    def finalize_execution(cls, execution: JobExecution, task_name: str, results: list):
        execution.execution_results = results
        execution.save(update_fields=["execution_results", "updated_at"])
        execution.refresh_from_db()
        if execution.status == ExecutionStatus.CANCELLED:
            logger.info(f"[{task_name}] 任务被取消: execution_id={execution.id}")
            return
        cls.update_execution_counts(execution)
        final_status = ExecutionStatus.FAILED if execution.failed_count > 0 else ExecutionStatus.SUCCESS
        cls.update_execution_status(execution, final_status, finished_at=timezone.now())
        logger.info(f"[{task_name}] 任务完成: execution_id={execution.id}, status={final_status}")

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

        # 调用 Ansible Executor
        executor = AnsibleExecutor(ansible_node_id)
        result = executor.adhoc(
            host_credentials=host_credentials,
            module=module,
            module_args=script_content,
            callback=callback_config,
            task_id=str(execution.id),
            timeout=execution.timeout,
        )

        logger.info(f"[{task_name}] Ansible 任务已提交: execution_id={execution.id}, result={result}")

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
        result = node_mgmt.node_list({"cloud_region_id": cloud_region_id, "is_container": True, "page": 1, "page_size": 1})
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
                    private_key = cls._get_ssh_private_key(target)
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

    @classmethod
    def get_ssh_credentials(cls, target_id: int) -> dict:
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
                "password": cls.decrypt_password(target.ssh_password),
                "private_key": private_key,
                "port": target.ssh_port,
                "node_id": target.node_id,  # 云区域 ID
            }
        except Target.DoesNotExist:
            return {}

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
