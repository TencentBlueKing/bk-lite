# -- coding: utf-8 --
# @File: nats.py
# @Time: 2025/9/4 11:36
# @Author: windyzhao
import nats_client
from apps.operation_analysis.constants.constants import PERMISSION_DIRECTORY, PERMISSION_DATASOURCE
from apps.operation_analysis.services.directory_service import DictDirectoryService


@nats_client.register
def get_operation_analysis_module_data(module, child_module, page, page_size, group_id):
    """
    获取运维分析模块数据的NATS接口
    :param module: 模块名称
    :param child_module: 子模块名称
    :param page: 页码
    :param page_size: 每页大小
    :param group_id: 组ID
    :return: 模块数据
    """

    result = DictDirectoryService.get_operation_analysis_module_data(module=module, child_module=child_module,page=page,
                                                                     page_size=page_size, group_id=group_id)
    return result


@nats_client.register
def get_operation_analysis_module_list():
    """
    获取运维分析模块列表的NATS接口
    :return: 模块列表
    """
    result = [
        {"name": PERMISSION_DIRECTORY, "display_name": "目录", "children":  [
            {"name": "dashboard", "display_name": "仪表盘"},
            {"name": "topology", "display_name": "拓扑图"},
            {"name": "architecture", "display_name": "架构图"}
        ]},
        {"name": PERMISSION_DATASOURCE, "display_name": "数据源", "children": []},
    ]
    return result
