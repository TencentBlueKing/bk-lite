# -*- coding: utf-8 -*-
# @File：base.py.py
# @Time：2025/6/16 11:15
# @Author：bennie
from abc import ABC, abstractmethod
import json
from core.nats import NATSConfig
from nats.aio.client import Client as NATS
from plugins.base_utils import convert_to_prometheus_format
from sanic.log import logger


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

        # 直接使用 NATS 客户端
        config = NATSConfig.from_env()
        nc = NATS()

        try:
            await nc.connect(**config.to_connect_options())
            payload = json.dumps(exec_params).encode()

            # 使用较短的超时时间，避免长时间卡住
            response_msg = await nc.request(subject, payload=payload, timeout=30.0)
            response = json.loads(response_msg.data.decode())

            # 移除 nats-executor 返回的 instance_id，使用 Telegraf 配置中的 instance_id
            if isinstance(response, dict) and 'instance_id' in response:
                del response['instance_id']

            return response
        except Exception as e:
            logger.error(f"NATS request failed: {type(e).__name__}: {e}")
            raise
        finally:
            try:
                if not nc.is_closed:
                    await nc.drain()
            except Exception as e:
                logger.error(f"Error closing NATS connection: {e}")

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
        except Exception as err:
            import traceback
            logger.error(
                f"{self.__class__.__name__} main error! {traceback.format_exc()}")
        return None
