# -- coding: utf-8 --
# @File: physcial_server_info.py
# @Time: 2025/12/9 17:48
# @Author: roger
# !/usr/bin/python
# -*- coding: utf-8 -*-

from plugins.base import BaseSSHPlugin
from plugins.base_utils import convert_to_prometheus_format
from sanic.log import logger
import re
from typing import Dict, List, Any
import json

class PserverInfo(BaseSSHPlugin):
    """Class for collecting server information."""
    default_script_path = "plugins/shell/server_default_disover.sh"
    plugin_type = "physcial_server"
    
    async def list_all_resources(self):
        """
        Convert collected data to a standard format.
        """
        try:
            data = await self.exec_script()
            if "===" in data.get("result",''):
                parsed_data = parse_server_info(data.get("result",''))
                self_device = self.host
                disk_info = parsed_data.pop('disk')
                mem_info = parsed_data.pop('memory')
                nic_info = parsed_data.pop('nic')
                gpu_info = parsed_data.pop('gpu')
                return_data = {
                    self.plugin_type: [{"success": True, "result": json.dumps(parsed_data)}],
                    "disk": [{"result": json.dumps({**i, "self_device": self_device}), "success": True} for i in disk_info],
                    "memory": [{"result": json.dumps({**i, "self_device": self_device}), "success": True} for i in mem_info],
                    "nic": [{"result": json.dumps({**i, "self_device": self_device}), "success": True} for i in nic_info],
                    "gpu": [{"result": json.dumps({**i, "self_device": self_device}), "success": True} for i in gpu_info],
                }
                prometheus_data = convert_to_prometheus_format(return_data)
            else:
                prometheus_data = convert_to_prometheus_format(
                    {self.plugin_type: [data]})
            return prometheus_data
        except Exception as err:
            import traceback
            logger.error(
                f"{self.__class__.__name__} main error! {traceback.format_exc()}")
        return None
    

def parse_server_info(shell_output: str) -> Dict[str, Any]:
    """
    解析物理服务器shell输出为JSON格式

    基于 === section === 标记来识别不同类型的数据

    Args:
        shell_output: shell脚本的输出文本

    Returns:
        包含服务器信息的字典
    """
    result = {
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
        'GPU info': 'gpu'
    }

    return key == start_keys.get(section)