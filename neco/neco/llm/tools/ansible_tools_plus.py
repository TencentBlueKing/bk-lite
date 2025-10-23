import json
import os
import uuid
import asyncio
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
import ansible_runner

from loguru import logger

# 常量定义
DEFAULT_TIMEOUT = 60
ALLOWED_MODULES = {
    'ping', 'setup', 'shell', 'command', 'copy', 'file', 'service',
    'systemd', 'user', 'group', 'package', 'yum', 'apt'
}


class AnsibleRunner:
    """
    Ansible Runner 封装类，提供安全的 ansible 执行环境

    Args:
        inventory: 主机清单内容
        module: ansible 模块名
        module_args: 模块参数
        timeout: 执行超时时间（秒）
        extravars: 额外变量
        playbook_str: playbook 内容
        host_pattern: 主机模式
    """

    def __init__(
        self,
        inventory: Optional[str] = None,
        module: Optional[str] = None,
        module_args: Optional[str] = None,
        timeout: Optional[int] = None,
        extravars: Optional[Dict[str, Any]] = None,
        playbook_str: Optional[str] = None,
        host_pattern: str = "localhost",
        **kwargs
    ):
        # 使用临时目录，避免路径遍历漏洞
        self.private_data_path = tempfile.mkdtemp(prefix="ansible_")
        self.inventory = self._validate_inventory(inventory)
        self.module = self._validate_module(module)
        self.module_args = module_args or ""
        self.timeout = timeout or DEFAULT_TIMEOUT
        self.extravars = extravars or {}
        self.uuid = str(uuid.uuid4())
        self.host_pattern = host_pattern
        self.playbook_str = playbook_str
        self.inventory_path: Optional[str] = None
        self.playbook_path: Optional[str] = None
        self.rc: Optional[ansible_runner.RunnerConfig] = None
        self.runner: Optional[ansible_runner.Runner] = None

    def _validate_inventory(self, inventory: Optional[str]) -> Optional[str]:
        """验证 inventory 内容安全性"""
        if not inventory:
            return inventory

        # 基本安全检查：禁止路径遍历字符
        if any(danger in inventory for danger in ['..', '/', '\\']):
            raise ValueError(
                "Invalid inventory content: contains path traversal characters")

        return inventory

    def _validate_module(self, module: Optional[str]) -> Optional[str]:
        """验证模块名安全性"""
        if not module:
            return module

        # 检查是否在允许的模块列表中
        if module not in ALLOWED_MODULES:
            raise ValueError(
                f"Module '{module}' not allowed. Allowed modules: {list(ALLOWED_MODULES)}")

        return module

    def __enter__(self):
        """根据目录创建playbook和inventory文件"""
        try:
            # 确保私有数据目录存在
            os.makedirs(self.private_data_path, exist_ok=True)
            logger.info(
                f"Created ansible private data directory: {self.private_data_path}")

            # 创建 playbook 文件（修正文件扩展名）
            if self.playbook_str:
                playbook_dir = os.path.join(
                    self.private_data_path, self.uuid, "playbooks")
                os.makedirs(playbook_dir, exist_ok=True)
                # 修正：使用 .yml 扩展名而不是 .py
                self.playbook_path = os.path.join(playbook_dir, "main.yml")
                with open(self.playbook_path, 'w', encoding='utf-8') as f:
                    f.write(self.playbook_str)
                logger.info(f"Created playbook file: {self.playbook_path}")

            # 创建 inventory 文件
            if self.inventory:
                uuid_dir = os.path.join(self.private_data_path, self.uuid)
                os.makedirs(uuid_dir, exist_ok=True)
                self.inventory_path = os.path.join(uuid_dir, "inventory")
                with open(self.inventory_path, 'w', encoding='utf-8') as f:
                    # 安全处理 inventory 内容
                    inventory_content = self.inventory.replace(";", "\n")
                    f.write(inventory_content)
                logger.info(f"Created inventory file: {self.inventory_path}")

            # 配置 ansible runner
            self.rc = ansible_runner.RunnerConfig(
                private_data_dir=self.private_data_path,
                playbook=os.path.basename(
                    self.playbook_path) if self.playbook_path else None,
                inventory=self.inventory_path,
                extravars=self.extravars,
                timeout=self.timeout,
                module=self.module,
                module_args=self.module_args,
                json_mode=True,
                host_pattern=self.host_pattern,
            )
            self.rc.prepare()
            self.runner = ansible_runner.Runner(config=self.rc)
            return self

        except Exception as e:
            logger.error(f"Failed to initialize AnsibleRunner: {e}")
            # 清理已创建的文件
            self._cleanup_files()
            raise

    def _cleanup_files(self):
        """安全清理临时文件"""
        if not self.private_data_path:
            return

        try:
            # 安全检查：确保只清理我们创建的临时目录
            if self.private_data_path.startswith(tempfile.gettempdir()):
                import shutil
                shutil.rmtree(self.private_data_path, ignore_errors=True)
                logger.info(
                    f"Cleaned up ansible private data directory: {self.private_data_path}")
            else:
                logger.warning(
                    f"Skipped cleanup of non-temp directory: {self.private_data_path}")
        except Exception as e:
            logger.error(f"Failed to cleanup ansible files: {e}")

    def __exit__(self, exc_type, exc_val, exc_tb):
        """执行完成后清理临时文件"""
        self._cleanup_files()

        if exc_val:
            logger.error(f"AnsibleRunner执行失败: {exc_type.__name__}: {exc_val}")
        else:
            logger.info(f"AnsibleRunner执行完成, uuid: {self.uuid}")

    def run(self):
        """
        执行ansible runner
        """
        # 安全日志：避免泄露敏感信息
        extravars_summary = f"{len(self.extravars)} variables" if self.extravars else "no variables"
        logger.info(f"ansible running start, uuid: {self.uuid}, module: {self.module}, "
                    f"timeout: {self.timeout}, host_pattern: {self.host_pattern}, "
                    f"extravars: {extravars_summary}")

        if not self.runner:
            raise RuntimeError(
                "AnsibleRunner not properly initialized. Use context manager.")

        self.runner.run()
        logger.info(f"ansible execution completed, uuid: {self.uuid}")


@tool()
async def ansible_adhoc(config: RunnableConfig) -> str:
    """
    Ansible Ad-hoc command tool.

    安全执行 ansible ad-hoc 命令的工具。

    Args:
        config (RunnableConfig): 包含 ansible 命令配置的对象
            - module: ansible 模块名（必需，必须在允许列表中）
            - module_args: 模块参数（可选）
            - inventory: 主机清单（可选）
            - timeout: 超时时间，默认60秒（可选）

    Returns:
        str: ansible 执行结果的 JSON 字符串

    Raises:
        ValueError: 当模块名不在允许列表中或参数无效时
        RuntimeError: 当 ansible 执行失败时
    """
    try:
        module = config["configurable"].get("module")
        module_args = config["configurable"].get("module_args", "")
        inventory = config["configurable"].get("inventory")
        timeout = config["configurable"].get("timeout", DEFAULT_TIMEOUT)

        # 参数验证
        if not module:
            raise ValueError("module is required")

        # 确定主机模式
        host_pattern = "localhost" if not inventory else "*"

        # 使用线程池执行阻塞操作，避免阻塞事件循环
        def _run_ansible():
            with AnsibleRunner(
                module=module,
                module_args=module_args,
                timeout=timeout,
                host_pattern=host_pattern,
                inventory=inventory
            ) as runner:
                runner.run()
                return list(runner.runner.events)

        # 在线程池中执行，避免阻塞事件循环
        loop = asyncio.get_event_loop()
        events = await loop.run_in_executor(None, _run_ansible)

        return json.dumps(events, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"ansible_adhoc failed: {e}")
        raise RuntimeError(f"Ansible execution failed: {e}")
