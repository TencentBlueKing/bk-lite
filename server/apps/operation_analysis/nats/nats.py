# -- coding: utf-8 --
# @File: nats.py
# @Time: 2025/9/4 11:36
# @Author: windyzhao
import logging
from functools import lru_cache

import nats_client
from apps.operation_analysis.constants.constants import PERMISSION_DATASOURCE, PERMISSION_DIRECTORY
from apps.operation_analysis.nats.auth import allow_legacy_unsigned_requests, verify_module_data_request
from apps.operation_analysis.services.directory_service import DictDirectoryService

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _warn_legacy_unsigned_once():
    logger.warning("Accepted legacy unsigned operation analysis NATS request")


@nats_client.register
def get_operation_analysis_module_data(module, child_module, page, page_size, group_id, _internal_auth=None):
    """
    获取运维分析模块数据的NATS接口
    :param module: 模块名称
    :param child_module: 子模块名称
    :param page: 页码
    :param page_size: 每页大小
    :param group_id: 组ID
    :param _internal_auth: 服务端内部调用认证令牌
    :return: 模块数据
    """

    if not _internal_auth and allow_legacy_unsigned_requests():
        _warn_legacy_unsigned_once()
    else:
        verify_module_data_request(
            _internal_auth,
            module=module,
            child_module=child_module,
            page=page,
            page_size=page_size,
            group_id=group_id,
        )

    result = DictDirectoryService.get_operation_analysis_module_data(
        module=module, child_module=child_module, page=page, page_size=page_size, group_id=group_id
    )
    return result


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
