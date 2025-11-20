# -- coding: utf-8 --
# @File: host_info.py
# @Time: 2025/5/6 17:48
# @Author: windyzhao
# !/usr/bin/python
# -*- coding: utf-8 -*-

from plugins.base import BaseSSHPlugin
from plugins.base_utils import convert_to_prometheus_format
from sanic.log import logger


class HostInfo(BaseSSHPlugin):
    """Class for collecting host information."""
    default_script_path = "plugins/shell/host_default_discover.sh"
    plugin_type = "host"

    async def list_all_resources(self):
        """
        重写父类方法,添加主机数据有效性检查
        只有采集成功的主机数据才会被推送到VictoriaMetrics
        """
        try:
            data = await self.exec_script()

            # 检查数据有效性: 必须是字典且不为空
            if not isinstance(data, dict) or not data:
                logger.warning(
                    f"Skipping empty or invalid data for {self.host}")
                return None

            # 主机信息采集必须包含关键字段才算成功
            required_fields = ["hostname", "os_type", "cpu_cores"]
            has_required = any(field in data for field in required_fields)

            if not has_required:
                logger.warning(
                    f"Skipping invalid host data for {self.host} - missing required fields")
                return None

            # 数据有效,添加标识字段
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
                f"Error collecting host info for {self.host}: {traceback.format_exc()}")
            return None
