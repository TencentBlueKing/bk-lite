# -*- coding: utf-8 -*-
"""OceanBase Information Collector (G5.2 占位 stub)。

**硬约束**:OceanBase 需 license + Python SDK `pyobclient` 不在 pyproject 默认依赖中。
- SDK:`pyobclient` 是蚂蚁官方 Python 客户端,需 OBProxy 中转
- 真采集路径:amd64 CI runner + OceanBase 镜像(含 OBProxy/SQL 引擎)+ 自备 license

**fixture 验证**:catalog 注册 + plugin stub 校验通过,真采集阻塞于 SDK + 镜像 license。
"""
import logging

logger = logging.getLogger(__name__)


class OceanbaseInfo:
    """采集 oceanbase 实例配置信息 (G5.2 占位 stub;license + 镜像 阻塞)。"""

    def __init__(self, kwargs):
        self.kwargs = kwargs
        self.host = kwargs.get("host", "localhost")
        self.port = int(kwargs.get("port", 2881))  # OBProxy 默认端口
        self.user = kwargs.get("user", "")
        self.password = kwargs.get("password", "")
        self.tenant = kwargs.get("tenant", "sys")

    def list_all_resources(self):
        """G5.2 占位实现:OceanBase 镜像 license 不可达 + pyobclient SDK 未装,返回空 list。

        修复路径:
        1. 拉 OceanBase 镜像 `obpilot/oceanbase-ce:latest`(社区版无需 license)
        2. 启 OBProxy + observer cluster
        3. `pip install pyobclient`
        4. 实现租户 / 资源池 / 数据库 列表采集
        """
        logger.warning(
            "G5.2 oceanbase collector blocked: community image + pyobclient SDK "
            "need setup on amd64 CI; see phase5-execution-report 2026-07-08"
        )
        return []