# -*- coding: utf-8 -*-
"""InterSystems IRIS Information Collector (G5.2 占位 stub)。

**硬约束**:InterSystems IRIS Python driver 公开渠道不完整 + Community Edition 镜像受限。
- driver:`intersystems-irispython` 或 `IRISClient` 需 InterSystems 开发者账号
- 镜像:`intersystems/iris-community:latest` Docker Hub 可达,但需注册账号
- 真采集路径:amd64 CI runner + InterSystems 开发者账号 + driver 安装

**fixture 验证**:catalog 注册 + plugin stub 校验通过,真采集阻塞于 driver + 账号。
"""
import logging

logger = logging.getLogger(__name__)


class IrisInfo:
    """采集 iris 实例配置信息 (G5.2 占位 stub;driver + 账号 阻塞)。"""

    def __init__(self, kwargs):
        self.kwargs = kwargs
        self.host = kwargs.get("host", "localhost")
        self.port = int(kwargs.get("port", 1972))  # IRIS SuperServer port
        self.user = kwargs.get("user", "_SYSTEM")
        self.password = kwargs.get("password", "")
        self.namespace = kwargs.get("namespace", "USER")

    def list_all_resources(self):
        """G5.2 占位实现:InterSystems IRIS Python driver 不可达,返回空 list。

        修复路径(需用户提供 InterSystems 账号):
        1. 注册 InterSystems 开发者账号(免费)
        2. 拉 `intersystems/iris-community:latest` 镜像
        3. 装 `pip install irisnative` 或 `pip install intersystems-irispython`
        4. 实现 namespace / table / global 列表采集
        """
        logger.warning(
            "G5.2 iris collector blocked: InterSystems IRIS Python driver + "
            "community image need developer account; see phase5-execution-report 2026-07-08"
        )
        return []