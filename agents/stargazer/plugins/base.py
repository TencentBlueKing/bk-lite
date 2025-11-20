# -*- coding: utf-8 -*-
# @File：base.py.py
# @Time：2025/6/16 11:15
# @Author：bennie
from abc import ABC, abstractmethod
import json
from core.nats import get_nats
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
        # 使用全局 NATS 实例而不是创建新的客户端
        self.nats_client = get_nats()

    async def connect_nats(self):
        """异步连接 NATS - 已废弃，使用全局实例"""
        pass

    async def close_nats(self):
        """异步关闭 NATS - 已废弃，使用全局实例"""
        pass

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

        try:
            response = await self.nats_client.request(subject=subject, data=exec_params, timeout=60.0)
        except Exception as e:
            logger.error(
                f"Remote execution request failed: {type(e).__name__}: {e}")
            raise

        # 检查执行是否成功
        if not response.get("success", True):
            error_msg = response.get("error", "Unknown error")
            logger.error(f"Remote execution failed: {error_msg}")
            raise Exception(f"Remote execution failed: {error_msg}")

        if isinstance(response.get("result"), str):
            response["result"] = response["result"].replace(
                "{{bk_host_innerip}}", self.host)
        try:
            resp = json.loads(response["result"])
        except Exception:  # noqa
            import traceback
            logger.error(
                f"exec_script json.loads error: {traceback.format_exc()}, response: {response}")
            resp = {}
        return resp

    async def list_all_resources(self):
        """
        Convert collected data to a standard format.
        """
        try:
            data = await self.exec_script()

            # 为数据添加必要的标识字段,用于CMDB自动发现
            if isinstance(data, dict):
                data['instance_id'] = f"{self.node_id}_{self.host}"
                data['host'] = self.host
                if 'inst_name' not in data:
                    data['inst_name'] = self.host

            prometheus_data = convert_to_prometheus_format(
                {self.plugin_type: [data]})
            return prometheus_data
        except Exception as err:
            import traceback
            logger.error(
                f"{self.__class__.__name__} main error! {traceback.format_exc()}")
            return None
