# -- coding: utf-8 --
# @File: physcial_server_info.py.py
# @Time: 2025/12/25 11:14
# @Author: windyzhao
import asyncio
import json
from typing import Any, Dict

from plugins.inputs.physcial_server.server_info_parse import parse_server_info
from plugins.script_executor import SSHPlugin
from sanic.log import logger


class PhyscialServerInfo(SSHPlugin):
    async def list_all_resources(self, need_raw=False):
        """
        Convert collected data to a standard format.
        """
        model_id = self.model_id or "physcial_server"
        try:
            data = await super().list_all_resources(need_raw=True)
            if "===" in data.get("result", ""):
                parsed_data = parse_server_info(data.get("result", ""))
                self_device = self.host
                disk_info = parsed_data.pop("disk")
                mem_info = parsed_data.pop("memory")
                nic_info = parsed_data.pop("nic")
                gpu_info = parsed_data.pop("gpu")
                return_data = {
                    model_id: [parsed_data],
                    "disk": [{**i, "self_device": self_device} for i in disk_info],
                    "memory": [{**i, "self_device": self_device} for i in mem_info],
                    "nic": [{**i, "self_device": self_device} for i in nic_info],
                    "gpu": [{**i, "self_device": self_device} for i in gpu_info],
                }
                result = {"success": True, "result": return_data}
            else:
                result = {"success": True, "result": {model_id: [{}]}}
        except Exception as err:
            import traceback

            logger.error(f"{self.__class__.__name__} main error! {traceback.format_exc()}")
            result = {"result": {"cmdb_collect_error": str(err)}, "success": False}
        return result


class PhyscialServerIPMIInfo:
    def __init__(self, kwargs):
        self.host = kwargs.get("host", "")
        self.port = int(kwargs.get("port", 623))
        self.username = kwargs.get("username", kwargs.get("user", ""))
        self.password = kwargs.get("password", "")
        self.privilege = kwargs.get("privilege")
        self.model_id = kwargs.get("model_id", "physcial_server")

    async def list_all_resources(self):
        return await asyncio.to_thread(self._list_all_resources_sync)

    def _list_all_resources_sync(self):
        try:
            try:
                from pyghmi.ipmi.command import Command
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError("pyghmi is required for physcial_server IPMI collection") from exc

            # 这里只做带外 identity / FRU 风格数据采集，不尝试补齐 SSH 路径负责的 disk/memory/nic/gpu。
            command = Command(
                bmc=self.host,
                userid=self.username,
                password=self.password,
                port=self.port,
                privlevel=self.privilege,
            )
            inventory = dict(command.get_inventory())
            system_info = inventory.get("System", {}) or {}

            result_data = {
                # 返回字段直接对齐 physcial_server IPMI 白名单，便于后续 formatter 做最小映射。
                "ip_addr": self.host,
                "port": self.port,
                "serial_number": first_value(system_info, "Serial Number"),
                "model": first_value(system_info, "Model", "Product name"),
                "brand": first_value(system_info, "Manufacturer"),
                "asset_code": first_value(system_info, "Asset Number"),
                "board_vendor": first_value(system_info, "Board manufacturer"),
                "board_model": first_value(system_info, "Board model", "Board product name"),
                "board_serial": first_value(system_info, "Board serial number"),
                "raw_payload": json.dumps(system_info, ensure_ascii=False),
            }
            return {
                "success": True,
                "result": {
                    self.model_id: [result_data],
                },
            }
        except Exception as err:  # noqa: BLE001
            logger.error(f"{self.__class__.__name__} main error! {err}")
            return {"result": {"cmdb_collect_error": str(err)}, "success": False}


def first_value(data: Dict[str, Any], *keys: str):
    """按候选字段顺序取第一个非空值，用于兼容不同厂商 FRU/inventory 返回的字段名差异。"""
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return ""
