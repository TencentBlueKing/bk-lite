from apps.rpc.base import RpcClient


class Executor(object):
    def __init__(self, instance_id):
        """
        命令执行客户端
        :param instance_id: 执行器实例ID
        """
        self.instance_id = instance_id
        self.local_client = RpcClient('local.execute')
        self.ssh_client = RpcClient('ssh.execute')
        self.download_to_local_client = RpcClient('download.local')
        self.download_to_remote_client = RpcClient('download.remote')

    def execute_local(self, command, timeout=60):
        """
        执行本地命令
        :param command: 要执行的命令
        :param timeout: 执行超时时间(秒)
        :return: 命令执行结果
        """
        request_data = {
            "command": command,
            "execute_timeout": timeout
        }
        return_data = self.local_client.run(self.instance_id, request_data, _timeout=timeout)
        return return_data

    def execute_ssh(self, command, host, username, password=None, key_file=None, timeout=60):
        """
        通过SSH执行远程命令
        :param command: 要执行的命令
        :param host: 远程主机地址
        :param username: SSH用户名
        :param password: SSH密码(可选)
        :param key_file: SSH密钥文件路径(可选)
        :param timeout: 执行超时时间(秒)
        :return: 命令执行结果
        """
        request_data = {
            "command": command,
            "host": host,
            "user": username,
            "execute_timeout": timeout
        }

        # 添加可选参数
        if password:
            request_data["password"] = password
        if key_file:
            request_data["key_file"] = key_file

        return_data = self.ssh_client.run(self.instance_id, request_data, _timeout=timeout)
        return return_data

    def download_to_local(self, bucket_name, file_key, file_name, target_path, timeout=60):
        """
        下载文件
        :param bucket_name: 存储桶名称
        :param file_key: 文件在存储桶中的键
        :param file_name: 文件名称
        :param target_path: 本地目标路径
        :param timeout: 执行超时时间(秒)
        :return: 下载结果
        """
        request_data = {
            "bucket_name": bucket_name,
            "file_key": file_key,
            "file_name": file_name,
            "target_path": target_path,
            "execute_timeout": timeout
        }
        return_data = self.download_to_local_client.run(self.instance_id, request_data, _timeout=timeout)
        return return_data

    def download_to_remote(self, bucket_name, file_key, file_name, target_path, host, username, password=None, timeout=60):
        """
        下载文件到远程
        :param bucket_name: 存储桶名称
        :param file_key: 文件在存储桶中的键
        :param file_name: 文件名称
        :param target_path: 远程目标路径
        :param host: 远程主机地址
        :param username: SSH用户名
        :param password: SSH密码(可选)
        :param timeout: 执行超时时间(秒)
        :return: 下载结果
        """
        request_data = {
            "bucket_name": bucket_name,
            "file_key": file_key,
            "file_name": file_name,
            "target_path": target_path,
            "host": host,
            "user": username,
            "execute_timeout": timeout,
        }
        # 添加可选参数
        if password:
            request_data["password"] = password
        return_data = self.download_to_remote_client.run(self.instance_id, request_data, _timeout=timeout)
        return return_data
