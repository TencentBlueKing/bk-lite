# -*- coding: utf-8 -*-
# @File：base.py.py
# @Time：2025/6/16 11:15
# @Author：bennie
from abc import ABC, abstractmethod
import json
from core.nast_request import NATSClient
from plugins.base_utils import convert_to_prometheus_format
from sanic.log import logger


class BasePlugin(ABC):

    @abstractmethod
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
        self.nats_client = NATSClient()

    async def connect_nats(self):
        """异步连接 NATS"""
        await self.nats_client.connect()

    async def close_nats(self):
        """异步关闭 NATS"""
        await self.nats_client.close()

    def get_script_path(self):
        assert self.default_script_path is not None, "default_script_path is not defined"
        return self.default_script_path

    @property
    @abstractmethod
    def plugin_type(self):
        pass

    @property
    def nast_id(self):
        """
        生成NATS ID
        :return:
        """
        return "ssh.execute" if self.username else "local.execute"

    @property
    def script(self):
        with open(self.get_script_path(), "r", encoding="utf-8") as f:
            return f.read()


    def format_params(self):
        """
        格式化参数
        :return:
        """
        script_params = {
            "command": self.command,
            "port": self.port,
        }
        if self.username:
            script_params["user"] = self.username
            script_params["username"] = self.username
            script_params["password"] = self.password
            script_params["host"] = self.host
        if self.time_out:
            script_params["execute_timeout"] = self.time_out
        return script_params

    async def exec_script(self):
        """
        调用 NATS 执行脚本
        """
        exec_params = {
            "args": [self.format_params()],
            "kwargs": {}
        }
        subject = f"{self.nast_id}.{self.node_id}"
        response = await self.nats_client.request(subject=subject, params=exec_params)  # 使用 await 调用异步方法
        if isinstance(response["result"], str):
            response["result"] = response["result"].replace("{{bk_host_innerip}}", self.host)
        return json.loads(response["result"])

    async def list_all_resources(self):
        """
        Convert collected data to a standard format.
        """
        try:
            await self.connect_nats()  # 异步连接 NATS
            data = await self.exec_script()  # 使用 await 获取执行结果
            prometheus_data = convert_to_prometheus_format({self.plugin_type: [data]})
            return prometheus_data
        except Exception as err:
            import traceback
            logger.error(f"{self.__class__.__name__} main error! {traceback.format_exc()}")
        finally:
            await self.close_nats()
        return None