# -*- coding: utf-8 -*-
# @File：base.py.py
# @Time：2025/6/16 11:15
# @Author：bennie
import os
import json
from abc import ABC, abstractmethod
from sanic.log import logger
from core.nats_utils import nats_request
from plugins.base_utils import convert_to_prometheus_format


class BasePlugin(ABC):

    def exec_script(self):
        raise NotImplementedError("exec_script is not implemented")

    def list_all_resources(self):
        raise NotImplementedError("list_all_resources is not implemented")


class BaseSSHPlugin(BasePlugin):
    default_script_path = None

    def __init__(self, params: dict):
        self.node_id = params["node_id"]
        self.host = params.get("host", "")
        self.username = params.get("username")
        self.password = params.get("password")
        self.time_out = int(params.get("execute_timeout", 60))
        self.command = params.get("command", self.script)
        self.port = int(params.get("port", 22))
        self._host_info = None  # 延迟加载

    def get_script_path(self):
        assert self.default_script_path is not None, "default_script_path is not defined"
        return self.default_script_path

    @property
    def namespace(self):
        return os.getenv("NATS_NAMESPACE", "bklite")

    @property
    @abstractmethod
    def plugin_type(self):
        pass

    async def get_host_info(self):
        """获取并缓存主机信息"""
        if self._host_info is None:
            self._host_info = await self.get_node_host_info()
        return self._host_info

    async def get_node_host_info(self):
        """
        从节点管理查询这个IP
        {
            'success': True,
            'result': {
                'count': 1,
                'nodes': [{
                    'id': '6fcde36828614500a03504d76b33815d',
                    'name': '10.10.41.149-1',
                    'ip': '10.10.41.149',
                    'operating_system': 'linux',
                    'status': {},
                    'cloud_region': 1,
                    'updated_at': '2025-12-16T08:56:50+0000',
                    'organization': [1],
                    'install_method': 'auto',
                    'node_type': 'host'
                }]
            }
        }
        """
        if not self.host:
            return {}

        try:
            data = await self.get_node_info()
        except Exception as e:  # noqa
            import traceback
            logger.error(f"查询IP在节点管理数据失败！host={self.host}, error={traceback.format_exc()}")
            return {}

        if not data.get("success"):
            return {}

        nodes = data["result"]["nodes"]
        if not nodes:
            return {}

        node_info = nodes[0]
        return node_info

    @staticmethod
    def nast_id(host_info):
        """
        生成NATS ID
        依据是否有host_info来决定使用本地执行还是SSH执行
        :param host_info:
        :return:
        """
        if host_info:
            return "local.execute"

        return "ssh.execute"

    @property
    def script(self):
        with open(self.get_script_path(), "r", encoding="utf-8") as f:
            return f.read()

    def format_params(self, host_info):
        """
        格式化参数 nats就不用走凭据
        :return:
        """
        script_params = {
            "command": self.command,
            "port": self.port,
        }

        if self.time_out:
            script_params["execute_timeout"] = self.time_out

        if not host_info and self.username:
            script_params["user"] = self.username
            script_params["username"] = self.username
            script_params["password"] = self.password
            script_params["host"] = self.host

        return script_params

    async def exec_script(self):
        """
        调用 NATS 执行脚本
        """
        host_info = await self.get_host_info()
        if host_info and host_info.get("operating_system") == "windows":
            raise RuntimeError("当前节点为Windows系统，无法使用SSH方式采集数据，请使用WinRM方式采集！")

        exec_params = {
            "args": [self.format_params(host_info)],
            "kwargs": {}
        }
        subject = f"{self.nast_id(host_info)}.{self.node_id}"
        payload = json.dumps(exec_params).encode()

        # 使用通用的 NATS 请求方法
        response = await nats_request(subject, payload=payload, timeout=self.time_out)

        # 移除 nats-executor 返回的 instance_id，使用 Telegraf 配置中的 instance_id
        if isinstance(response, dict) and 'instance_id' in response:
            del response['instance_id']

        return response

    async def list_all_resources(self):
        """
        Convert collected data to a standard format.
        """

        try:
            data = await self.exec_script()
            data['cmdbhost'] = self.host
            prometheus_data = convert_to_prometheus_format(
                {self.plugin_type: [data]})
            return prometheus_data
        except Exception:
            import traceback
            logger.error(
                f"{self.__class__.__name__} main error! {traceback.format_exc()}")
        return None

    async def get_node_info(self):
        """
        获取节点列表
        :return:
        """
        exec_params = {
            "args": [{"ip": self.host}],
            "kwargs": {}
        }
        subject = f"{self.namespace}.node_list"
        payload = json.dumps(exec_params).encode()

        # 使用通用的 NATS 请求方法
        response = await nats_request(subject, payload=payload, timeout=30.0)
        return response
