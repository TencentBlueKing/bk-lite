# -- coding: utf-8 --
# @File: physcial_server_info.py.py
# @Time: 2025/12/25 11:14
# @Author: windyzhao
import asyncio
import re
import json
from typing import Dict, Any
from sanic.log import logger

from plugins.script_executor import SSHPlugin


class PhyscialServerInfo(SSHPlugin):

    async def list_all_resources(self, need_raw=False):
        """
        Convert collected data to a standard format.
        """
        model_id = self.model_id or "physcial_server"
        try:
            data = await super().list_all_resources(need_raw=True)
            if "===" in data.get("result", ''):
                parsed_data = parse_server_info(data.get("result", ''))
                self_device = self.host
                disk_info = parsed_data.pop('disk')
                mem_info = parsed_data.pop('memory')
                nic_info = parsed_data.pop('nic')
                gpu_info = parsed_data.pop('gpu')
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
        self.host = kwargs.get('host', '')
        self.port = int(kwargs.get('port', 623))
        self.username = kwargs.get('username', kwargs.get('user', ''))
        self.password = kwargs.get('password', '')
        self.privilege = kwargs.get('privilege')
        self.model_id = kwargs.get('model_id', 'physcial_server')

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
            system_info = inventory.get('System', {}) or {}

            result_data = {
                # 返回字段直接对齐 physcial_server IPMI 白名单，便于后续 formatter 做最小映射。
                'ip_addr': self.host,
                'port': self.port,
                'serial_number': first_value(system_info, 'Serial Number'),
                'model': first_value(system_info, 'Model', 'Product name'),
                'brand': first_value(system_info, 'Manufacturer'),
                'asset_code': first_value(system_info, 'Asset Number'),
                'board_vendor': first_value(system_info, 'Board manufacturer'),
                'board_model': first_value(system_info, 'Board model', 'Board product name'),
                'board_serial': first_value(system_info, 'Board serial number'),
                'raw_payload': json.dumps(system_info, ensure_ascii=False),
            }
            return {
                'success': True,
                'result': {
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
        if value not in (None, ''):
            return value
    return ''


def parse_server_info(shell_output: str) -> Dict[str, Any]:
    """
    解析物理服务器shell输出为JSON格式

    基于 === section === 标记来识别不同类型的数据

    Args:
        shell_output: shell脚本的输出文本

    Returns:
        包含服务器信息的字典
    """
    result: Dict[str, Any] = {
        "disk": [],
        "memory": [],
        "nic": [],
        "gpu": []
    }

    lines = shell_output.strip().split('\n')
    current_section = None
    current_item = {}

    # 定义哪些section的数据应该存为列表
    list_sections = {
        'disk_info': 'disk',
        'mem_info': 'memory',
        'NIC info': 'nic',
        'GPU info': 'gpu'
    }

    for line in lines:
        line = line.strip()
        # 跳过空行和无关内容
        if not line or line.startswith('【') or line.startswith('---'):
            continue

        # 检测section标记 === xxx ===
        if line.startswith('===') and line.endswith('==='):
            # 保存上一个section的item
            if current_section and current_item:
                if current_section in list_sections:
                    result[list_sections[current_section]].append(current_item)
                current_item = {}

            # 提取新的section名称
            section_match = re.search(r'===\s*(.+?)\s*===', line)
            if section_match:
                current_section = section_match.group(1).strip()
            continue

        # 解析键值对
        if '=' in line and current_section:
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip()

            # 根据当前section判断数据归属
            if current_section in list_sections:
                # 需要存为列表的section
                # 检测是否是新对象的开始(通常是第一个字段)
                if current_item and is_new_item_start(key, current_section):
                    result[list_sections[current_section]].append(current_item)
                    current_item = {}
                current_item[key] = value
            else:
                # 直接合并到根对象的section
                result[key] = value

    # 处理最后一个item
    if current_section and current_item:
        if current_section in list_sections:
            result[list_sections[current_section]].append(current_item)

    return result


def is_new_item_start(key: str, section: str) -> bool:
    """
    判断当前key是否是新对象的开始

    Args:
        key: 当前的键名
        section: 当前所在的section

    Returns:
        是否是新对象的第一个字段
    """
    # 定义每个section中标识新对象开始的字段
    start_keys = {
        'disk_info': 'disk_name',
        'mem_info': 'mem_locator',
        'NIC info': 'nic_pci_addr',
        'GPU info': 'gpu_name'
    }

    return key == start_keys.get(section)
