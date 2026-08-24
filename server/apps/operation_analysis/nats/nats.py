# -- coding: utf-8 --
# @File: nats.py
# @Time: 2025/9/4 11:36
# @Author: windyzhao
import nats_client
from apps.operation_analysis.constants.constants import PERMISSION_DATASOURCE, PERMISSION_DIRECTORY
from apps.operation_analysis.nats.auth import verify_module_data_request
from apps.operation_analysis.services.directory_service import DictDirectoryService


@nats_client.register
def get_operation_analysis_module_data_v2(module, child_module, page, page_size, group_id, _internal_auth=None):
    """版本化的签名查询入口，避免滚动发布时新 payload 被旧 handler 拒绝。"""

    request_params = verify_module_data_request(
        _internal_auth,
        module=module,
        child_module=child_module,
        page=page,
        page_size=page_size,
        group_id=group_id,
    )
    return DictDirectoryService.get_operation_analysis_module_data(**request_params)


@nats_client.register
def get_operation_analysis_module_list():
    """
    获取运维分析模块列表的NATS接口
    :return: 模块列表
    """
    result = [
        {
            "name": PERMISSION_DIRECTORY,
            "display_name": "目录",
            "children": [
                {"name": "dashboard", "display_name": "仪表盘"},
                {"name": "topology", "display_name": "拓扑图"},
                {"name": "architecture", "display_name": "架构图"},
            ],
        },
        {"name": PERMISSION_DATASOURCE, "display_name": "数据源", "children": []},
    ]
    return result
