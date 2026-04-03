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
        host_credentials=None,
        private_key_content=None,
        private_key_passphrase=None,
        hosts="all",
        module="ping",
        module_args="",
        extra_vars=None,
        callback=None,
        task_id=None,
        timeout=60,
    ):
        """
        执行 ansible ad-hoc。

        参数说明：
        :param inventory: inventory 文件路径或 inline inventory（可选）
        :param inventory_content: inventory 内容（可选，推荐多主机场景使用）
        :param host_credentials: 多主机结构化凭据列表（可选）
            结构示例：
            [
              {
                "host": "10.0.0.1",
                "user": "root",
                "password": "PassA",
                "connection": "ssh",
                "port": 22
              },
              {
                "host": "10.0.0.2",
                "user": "ubuntu",
                "private_key_content": "-----BEGIN ...",
                "private_key_passphrase": "xxx",
                "connection": "ssh",
                "port": 22
              }
            ]
        :param private_key_content: SSH 私钥内容（可选，PEM）
            - 这是“全局默认私钥”注入方式
            - 多主机且密钥不同，建议在 inventory_content 中按 host 单独指定
        :param private_key_passphrase: SSH 私钥口令（可选）
        :param hosts: 主机匹配表达式，默认 all
        :param module: ansible 模块名，默认 ping
        :param module_args: 模块参数
        :param extra_vars: 额外变量字典
        :param callback: 回调配置，支持两种格式
            - {"subject":"job.ansible_task_callback","timeout":10}
            - {"namespace":"job","method_name":"ansible_task_callback","instance_id":"server","timeout":10}
        :param task_id: 任务 ID（可选，不传自动生成）
        :param timeout: 执行超时时间（秒）
        :return: 任务受理结果（accepted + task_id）

        多目标机器凭据不一致示例（推荐：inventory_content 按 host 传）：

        inventory_content 示例：
        [targets]
        10.0.0.1 ansible_user=root ansible_password=PassA ansible_connection=ssh ansible_port=22
        10.0.0.2 ansible_user=ubuntu ansible_ssh_private_key_file=/path/key_b.pem ansible_connection=ssh ansible_port=22
        10.0.0.3 ansible_user=ec2-user ansible_password=PassC ansible_connection=ssh ansible_port=2222

        调用示例：
        executor.adhoc(
            inventory_content=inventory_content,
            hosts="targets",
            module="ping",
            module_args="",
            extra_vars={},
            callback={"subject": "job.ansible_task_callback", "timeout": 10},
            timeout=120,
        )
        """
        if not inventory and not inventory_content:
            if not host_credentials:
                raise ValueError("inventory or inventory_content or host_credentials is required")

        request_data = {
            "inventory": inventory,
            "inventory_content": inventory_content,
            "host_credentials": host_credentials or [],
            "private_key_content": private_key_content,
            "private_key_passphrase": private_key_passphrase,
            "hosts": hosts,
            "module": module,
            "module_args": module_args,
            "extra_vars": extra_vars or {},
            "callback": callback or {},
            "task_id": task_id or uuid.uuid4().hex,
            "execute_timeout": timeout,
        }
        return_data = self.adhoc_client.run(self.instance_id, request_data, _timeout=timeout)
        return return_data

    def playbook(
        self,
        playbook_path="",
        inventory="",
        extra_vars=None,
        playbook_content=None,
        inventory_content=None,
        host_credentials=None,
        private_key_content=None,
        private_key_passphrase=None,
        files=None,
        file_distribution=None,
        callback=None,
        task_id=None,
        timeout=600,
    ):
        """
        执行 ansible-playbook。

        参数说明：
        :param playbook_path: playbook 路径（可选）
        :param inventory: inventory 文件路径或 inline inventory（可选）
        :param extra_vars: 额外变量字典
        :param playbook_content: playbook 内容（可选）
        :param inventory_content: inventory 内容（可选，推荐多主机场景）
        :param host_credentials: 多主机结构化凭据列表（可选，结构同 adhoc）
        :param private_key_content: SSH 私钥内容（可选，PEM）
            - 作为“全局默认私钥”注入
            - 多主机密钥差异建议在 inventory_content 中按 host 指定
        :param private_key_passphrase: SSH 私钥口令（可选）
        :param callback: 回调配置，支持两种格式
            - {"subject":"job.ansible_task_callback","timeout":10}
            - {"namespace":"job","method_name":"ansible_task_callback","instance_id":"server","timeout":10}
        :param task_id: 任务 ID（可选，不传自动生成）
        :param timeout: 执行超时时间（秒）
        :return: 任务受理结果（accepted + task_id）

        多目标机器凭据不一致示例：
        1) 把每台机器的账号/密码/密钥配置在 inventory_content 中；
        2) playbook_content 只关注业务逻辑。

        调用示例：
        executor.playbook(
            playbook_content="- hosts: targets\n  gather_facts: false\n  tasks:\n    - ping:\n",
            inventory_content=(
                "[targets]\n"
                "10.0.0.1 ansible_user=root ansible_password=PassA ansible_connection=ssh\n"
                "10.0.0.2 ansible_user=ubuntu ansible_ssh_private_key_file=/path/key_b.pem ansible_connection=ssh\n"
            ),
            extra_vars={},
            callback={"subject": "job.ansible_task_callback", "timeout": 10},
            timeout=300,
        )
        """
        if not playbook_path and not playbook_content and not file_distribution:
            raise ValueError("playbook_path or playbook_content is required")
        if not inventory and not inventory_content:
            if not host_credentials:
                raise ValueError("inventory or inventory_content or host_credentials is required")

        request_data = {
            "playbook_path": playbook_path,
            "playbook_content": playbook_content,
            "inventory": inventory,
            "inventory_content": inventory_content,
            "host_credentials": host_credentials or [],
            "private_key_content": private_key_content,
            "private_key_passphrase": private_key_passphrase,
            "files": files or [],
            "file_distribution": file_distribution or {},
            "extra_vars": extra_vars or {},
            "callback": callback or {},
            "task_id": task_id or uuid.uuid4().hex,
            "execute_timeout": timeout,
        }
        return_data = self.playbook_client.run(self.instance_id, request_data, _timeout=timeout)
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
