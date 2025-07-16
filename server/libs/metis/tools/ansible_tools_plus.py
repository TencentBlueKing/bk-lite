import json
import os
import uuid

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
import ansible_runner

import logging

logger = logging.getLogger(__name__)


class AnsibleRunner():
    def __init__(self, inventory: str = None, module: str = None, module_args: str = None, timeout: int = None,
                 extravars: dict = None, playbook_str: str = None,
                 host_pattern: str = "localhost", **kwargs):

        self.private_data_path = os.environ.get('ANSIBLE_PRIVATE_DATA_DIR', os.path.join(os.getcwd(), 'ansible'))
        self.inventory = inventory
        self.module = module
        self.module_args = module_args
        self.timeout = timeout
        self.extravars = extravars
        self.uuid = str(uuid.uuid4())
        self.host_pattern = host_pattern
        self.playbook_str = playbook_str

    def __enter__(self):
        """根据目录创建playbook和inventory文件"""
        if not os.path.exists(self.private_data_path):
            os.makedirs(self.private_data_path)
        self.inventory_path = None
        self.playbook_path = None
        if self.playbook_str and not os.path.exists(os.path.join(self.private_data_path, self.uuid, "playbooks")):
            os.makedirs(os.path.join(self.private_data_path, self.uuid, "playbooks"))
            self.playbook_path = os.path.join(self.private_data_path,  self.uuid,"playbooks", "main.py")
            with open(self.playbook_path, 'w') as f:
                f.write(self.playbook_str)
        if self.inventory and not os.path.exists(os.path.join(self.private_data_path, self.uuid)):
            os.makedirs(os.path.join(self.private_data_path,self.uuid))
            self.inventory_path = os.path.join(self.private_data_path, self.uuid, "inventory")
            with open(self.inventory_path, 'w') as f:
                f.write(self.inventory.replace(";", "\n"))
        self.rc = ansible_runner.RunnerConfig(
            private_data_dir=self.private_data_path,
            playbook=self.playbook_path,
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

    def __exit__(self, exc_type, exc_val, exc_tb):
        """执行完成后删除playbook和inventory文件"""
        if os.path.exists(self.private_data_path):
            for root, dirs, files in os.walk(self.private_data_path, topdown=False):
                for name in files:
                    os.remove(os.path.join(root, name))
                for name in dirs:
                    os.rmdir(os.path.join(root, name))
            os.rmdir(self.private_data_path)
        if exc_val:
            logger.error(f"AnsibleRunner执行失败: {exc_val}")

    def run(self):
        """
        执行ansible runner
        """
        logger.info(f"ansible running start, uuid: {self.uuid}, module: {self.module}, module_args: {self.module_args}"
                    f", inventory: {self.inventory}, timeout: {self.timeout}, host_pattern: {self.host_pattern},"
                    f" extravars: {self.extravars}")
        self.runner.run()


@tool()
def ansible_adhoc(config: RunnableConfig):
    """
    Ansible Ad-hoc command tool.
    This tool allows you to run ad-hoc commands using Ansible.
    Args:
        config (RunnableConfig): Configuration for the Ansible command.
    Returns:
    """


    module = config["configurable"].get("module")
    module_args = config["configurable"].get("module_args", "")
    inventory = config["configurable"].get("inventory")

    if not inventory:
        host_pattern = "localhost"
    else:
        host_pattern = "*"
    if not module:
        raise ValueError("module is required")
    timeout = config["configurable"].get("timeout", 60)
    with AnsibleRunner(module=module, module_args=module_args, timeout=timeout, host_pattern=host_pattern,
                       inventory=inventory) as runner:
        runner.run()
        return json.dumps(list(runner.runner.events))
