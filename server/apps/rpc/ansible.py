import uuid

from apps.rpc.base import RpcClient


class AnsibleRpcClient(RpcClient):
    def __init__(self, namespace):
        self.namespace = namespace


class AnsibleExecutor(object):
    def __init__(self, instance_id):
        """
        Ansible 执行器 RPC 客户端
        :param instance_id: 执行器实例 ID
        """
        self.instance_id = instance_id
        self.adhoc_client = AnsibleRpcClient("ansible.adhoc")
        self.playbook_client = AnsibleRpcClient("ansible.playbook")

    def adhoc(
        self,
        inventory="",
        inventory_content=None,
        hosts="all",
        module="ping",
        module_args="",
        extra_vars=None,
        callback=None,
        task_id=None,
        timeout=60,
    ):
        """
        执行 ansible ad-hoc
        :param inventory: inventory 文件路径或 inline inventory（可选）
        :param inventory_content: inventory 内容（可选）
        :param hosts: 主机匹配表达式，默认 all
        :param module: ansible 模块名，默认 ping
        :param module_args: 模块参数
        :param extra_vars: 额外变量字典
        :param callback: 回调配置，示例：{"namespace":"bk_lite","method_name":"ansible_task_callback","instance_id":"server","timeout":10}
            或 {"subject":"callback.done.instance","timeout":10}
        :param task_id: 任务 ID（可选，不传自动生成）
        :param timeout: 超时时间（秒）
        :return: 任务受理结果
        """
        if not inventory and not inventory_content:
            raise ValueError("inventory or inventory_content is required")

        request_data = {
            "inventory": inventory,
            "inventory_content": inventory_content,
            "hosts": hosts,
            "module": module,
            "module_args": module_args,
            "extra_vars": extra_vars or {},
            "callback": callback or {},
            "task_id": task_id or uuid.uuid4().hex,
            "execute_timeout": timeout,
        }
        return_data = self.adhoc_client.run(
            self.instance_id, request_data, _timeout=timeout
        )
        return return_data

    def playbook(
        self,
        playbook_path="",
        inventory="",
        extra_vars=None,
        playbook_content=None,
        inventory_content=None,
        callback=None,
        task_id=None,
        timeout=600,
    ):
        """
        执行 ansible-playbook
        :param playbook_path: playbook 路径（可选）
        :param inventory: inventory 文件路径或 inline inventory（可选）
        :param extra_vars: 额外变量字典
        :param playbook_content: playbook 内容（可选）
        :param inventory_content: inventory 内容（可选）
        :param callback: 回调配置，示例：{"namespace":"bk_lite","method_name":"ansible_task_callback","instance_id":"server","timeout":10}
            或 {"subject":"callback.done.instance","timeout":10}
        :param task_id: 任务 ID（可选，不传自动生成）
        :param timeout: 超时时间（秒）
        :return: 任务受理结果
        """
        if not playbook_path and not playbook_content:
            raise ValueError("playbook_path or playbook_content is required")
        if not inventory and not inventory_content:
            raise ValueError("inventory or inventory_content is required")

        request_data = {
            "playbook_path": playbook_path,
            "playbook_content": playbook_content,
            "inventory": inventory,
            "inventory_content": inventory_content,
            "extra_vars": extra_vars or {},
            "callback": callback or {},
            "task_id": task_id or uuid.uuid4().hex,
            "execute_timeout": timeout,
        }
        return_data = self.playbook_client.run(
            self.instance_id, request_data, _timeout=timeout
        )
        return return_data

    def task_query(self, task_id, timeout=10):
        """
        查询异步任务状态
        :param task_id: 任务 ID
        :param timeout: 查询超时（秒）
        :return: 任务状态与结果
        """
        query_client = AnsibleRpcClient("ansible.task.query")
        request_data = {"task_id": task_id}
        return query_client.run(self.instance_id, request_data, _timeout=timeout)
